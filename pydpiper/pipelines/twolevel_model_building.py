#!/usr/bin/env python3

import copy
import os
import sys
import warnings

import numpy as np
from configargparse import Namespace, ArgParser
import pandas as pd
from pydpiper.pipelines.MAGeT import maget

from pydpiper.minc.analysis import determinants_at_fwhms
from pydpiper.minc.files import MincAtom
from pydpiper.minc.registration import (concat_xfmhandlers, invert_xfmhandler, mincresample_new, check_MINC_input_files)
from pydpiper.pipelines.MBM import mbm, mbm_parser, MBMConf
from pydpiper.execution.application import execute
from pydpiper.core.util import NamedTuple
from pydpiper.core.stages import Stages, Result
from pydpiper.core.arguments import (AnnotatedParser, CompoundParser, application_parser,
                                     execution_parser, registration_parser, parse, BaseParser, segmentation_parser)


TwoLevelConf = NamedTuple("TwoLevelConf", [("first_level_conf", MBMConf),
                                           ("second_level_conf", MBMConf)])


def two_level_pipeline(options : TwoLevelConf):

    if options.application.files:
        warnings.warn("Got extra arguments: '%s'" % options.application.files)
    with open(options.twolevel.csv_file, 'r') as f:
        try:
            files_df = pd.read_csv(filepath_or_buffer=f,
                                   usecols=['group', 'file'],
                                   converters={ 'file' : lambda f: MincAtom(f) })  # TODO pipeline_sub_dir?
        except AttributeError:
            warnings.warn("Something went wrong ... does your .csv file have `group` and `file` columns?")
            raise

    check_MINC_input_files(files_df.file.map(lambda x: x.path))

    return two_level(grouped_files_df=files_df, options=options)


def two_level(grouped_files_df, options : TwoLevelConf):
    """
    grouped_files_df - must contain 'group':<any comparable, sortable type> and 'file':MincAtom columns
    """
    s = Stages()

    first_level_results = (
        grouped_files_df
        .groupby('group', as_index=False, sort=False)       # the usual annoying pattern to do a aggregate with access
        .aggregate({ 'file' : lambda files: list(files) })  # to the groupby object's keys ... TODO: fix
        .rename(columns={ 'file' : "files" })
        .assign(build_model=lambda df:
                              df.apply(axis=1,
                                       func=lambda row:
                                              s.defer(mbm(imgs=row.files,
                                                          options=options,
                                                          prefix="%s" % row.group,
                                                          output_dir=os.path.join(
                                                              options.application.output_directory,
                                                              options.application.pipeline_name + "_first_level",
                                                              "%s_processed" % row.group)))))
        )
    # TODO replace .assign(...apply(...)...) with just an apply, producing a series right away?

    # FIXME right now the same options set is being used for both levels -- use options.first/second_level
    # TODO should there be a pride of models for this pipe as well ?
    second_level_options = copy.deepcopy(options)
    second_level_options.mbm.lsq6 = second_level_options.mbm.lsq6.replace(run_lsq6=False) #nuc=False, inormalize=False
    # NOTE: running lsq6_nuc_inorm here doesn't work in general (but possibly with rotational minctracc)
    # since the native-space initial model is used, but our images are
    # already in standard space(as we resampled there after the 1st-level lsq6).
    # On the other hand, we might want to run it here (although of course not nuc/inorm) in the future,
    # for instance given a 'pride' of models (one for each group).

    second_level_results = s.defer(mbm(imgs=first_level_results.build_model.map(lambda m: m.avg_img),
                                       options=second_level_options,
                                       prefix=os.path.join(options.application.output_directory,
                                                           options.application.pipeline_name + "_second_level")))

    # FIXME sadly, `mbm` doesn't return a pd.Series of xfms, so we don't have convenient indexing ...
    overall_xfms = [s.defer(concat_xfmhandlers([xfm_1, xfm_2]))
                    for xfms_1, xfm_2 in zip([r.xfms.lsq12_nlin_xfm for r in first_level_results.build_model],
                                             second_level_results.xfms.overall_xfm)
                    for xfm_1 in xfms_1]
    resample  = np.vectorize(mincresample_new, excluded={"extra_flags"})
    defer     = np.vectorize(s.defer)

    # TODO using the avg_img here is a bit clunky -- maybe better to propagate group indices ...
    # only necessary since `mbm` doesn't return DataFrames but namespaces ...
    first_level_determinants = pd.concat(list(first_level_results.build_model.apply(
                                                lambda x: x.determinants.assign(first_level_avg=x.avg_img))),
                                         ignore_index=True)

    resampled_determinants = (pd.merge(
        left=first_level_determinants,
        right=pd.DataFrame({'group_xfm' : second_level_results.xfms.overall_xfm})
              .assign(source=lambda df: df.group_xfm.apply(lambda r: r.source)),
        left_on="first_level_avg",
        right_on="source")
        .assign(resampled_log_full_det=lambda df: defer(resample(img=df.log_full_det,
                                                                 xfm=df.group_xfm.apply(lambda x: x.xfm),
                                                                 like=second_level_results.avg_img)),
                resampled_log_nlin_det=lambda df: defer(resample(img=df.log_nlin_det,
                                                                 xfm=df.group_xfm.apply(lambda x: x.xfm),
                                                                 like=second_level_results.avg_img))))
    # TODO only resamples the log determinants, but still a bit ugly ... abstract somehow?
    # TODO shouldn't be called resampled_determinants since this is basically the whole (first_level) thing ...

    inverted_overall_xfms = [s.defer(invert_xfmhandler(xfm)) for xfm in overall_xfms]

    overall_determinants = s.defer(determinants_at_fwhms(
                                     xfms=inverted_overall_xfms,
                                     inv_xfms=overall_xfms,
                                     blur_fwhms=options.mbm.stats.stats_kernels))

    # TODO return some MAGeT stuff from two_level function ??
    # FIXME running MAGeT from within the `two_level` function has the same problem as running it from within `mbm`:
    # it will now run when this pipeline is called from within another one (e.g., n-level), which will be
    # redundant, create filename clashes, etc. -- this should be moved to `two_level_pipeline`.
    if options.mbm.mbm.run_maget:
        maget_options = copy.deepcopy(options)
        maget_options.maget = options.mbm.maget
        del maget_options.mbm

        # again using a weird combination of vectorized and loop constructs ...
        s.defer(maget([xfm.resampled for _ix, m in first_level_results.iterrows()
                       for xfm in m.build_model.xfms.rigid_xfm],
                      options=maget_options,
                      prefix="%s_MAGeT" % options.application.pipeline_name,
                      output_dir=os.path.join(options.application.output_directory,
                                              options.application.pipeline_name + "_processed")))

    # TODO resampling to database model ...

    # TODO package up all transforms and first-level/resampled determinants into a couple tables and return them ...
    return Result(stages=s, output=NotImplemented)

# FIXME: better to replace --files by this for all/most pipelines;
# then we can enforce presence of metadata in the CSV file ... (pace MINC2)
def _mk_twolevel_parser(p):
    p.add_argument("--csv-file", dest="csv_file", type=str, required=True,
                   help="CSV file containing at least 'group' and 'file' columns")
    return p


_twolevel_parser = BaseParser(_mk_twolevel_parser(ArgParser(add_help=False)), group_name='twolevel')
twolevel_parser = AnnotatedParser(parser=_twolevel_parser, namespace="twolevel")


def main(args):
    p = CompoundParser(
          [execution_parser,
           application_parser,
           registration_parser,
           twolevel_parser,
           AnnotatedParser(parser=mbm_parser, namespace="mbm"),   # TODO use this before 1st-/2nd-level args
           # TODO to combine the information from all three MBM parsers,
           # could use `ConfigArgParse`r `_source_to_settings` (others?) to check whether an option was defaulted
           # or user-specified, allowing the first/second-level options to override the general mbm settings
           #AnnotatedParser(parser=mbm_parser, namespace="first_level", prefix="first-level"),
           #AnnotatedParser(parser=mbm_parser, namespace="second_level", prefix="second-level"),
           #stats_parser
           #segmentation_parser
           ])  # TODO add more stats parsers?

    options = parse(p, args[1:])

    execute(two_level_pipeline(options).stages, options)

if __name__ == "__main__":
    main(sys.argv)
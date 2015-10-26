'''
This file will contain argument option groups that can be used 
by PydPiper applications. Some option groups might be mandatory/highly
recommended to add to your application: e.g. the arguments that deal
with the execution of your application.
'''
from configargparse import ArgParser, Namespace
import time
import os
from pkg_resources import get_distribution

from atom.api import Atom, Enum, Instance

# TODO: should the pipeline-specific argument handling be located here
# or in that pipeline's module?  Makes more sense (general stuff
# can still go here)

class PydParser(ArgParser):
    """
    #>>> p = PydParser()
    #>>> g = p.add_argument_group("General", prefix='foo')
    #>>> g.add_argument('--bar', type=int)
    #>>> p.parse_args(['--foo-bar', '3'])
    #Namespace(foo_bar=3)
    """
    # Some sneakiness... override the format_epilog method
    # to return the epilog verbatim.
    # That way in the help message you can include an example
    # of what an lsq6/nlin protocol should look like, and this
    # won't be mangled when the parser calls `format_epilog`
    # when writing its help.
    def format_epilog(self, formatter):
        if not self.epilog:
            self.epilog = ""
        return self.epilog

def id(*args, **kwargs):
    return args, kwargs

# TODO: this API is rather unclear.  Better idea: make a class
#class parser(object):
#    def __init__(self, whatever):
#        # test that whatever actually makes sense
#p = parser({ 'application' :
#               [verbatim('--foo', type=int)],
#             'lsq12' :
#               [verbatim('--bar', type=str)],
#             'blah'  : [] })
#p(['--foo', '--bar'])

# my ideal API ...:
# would sets be semantically better here/below?
#applicationArguments = [id('--arg1'), id('--arg2')]
#lsq12Arguments       = [id('--bar', dest='wherever')]
# the important thing is that you can define such a thing
# WITHOUT specifying where the result is to go ...
#coreArgumentGroups = [(applicationArguments, 'application'),
#                      (executionArguments,   'execution'),
#                      (generalArguments,     'general')]
# argument sets plus prefix AND a namespace to parse into:
#parser = make_parser(coreArgumentGroups
#                   + [(chainArguments, 'chain')])
#result = parser(args)
#this doesn't work well since other fns like
#add_mutually_exclusive_group, etc., don't work.

#another possibility would be to post-process parser._actions
#but it's too late to do so since we don't know which group
#a given --whatever came from.  To fix this, we could make
#the addX functions take a group instead of a parser:
# def addExecutorArguments(g, *args, **kwargs):
#   g.add

def nullable_int(string):
    if string == "None":
        return None
    else:
        return int(string)

#FIXME is this approach general enough that it could work in a nested way,
#e.g., if two MBM calls within a single pipeline each want separate
#LSQ12 params? investigate ...
def make_parser(pcs): # [(???, str)] -> arglist -> Namespace(Namespace())
    """
    Parse args given a list of parserconfigs to generate a parser from and some args to parse.
    Note: the implementation is a huge hack--apologies for breakage
    """
    def parser(args):
        # TODO: code cleanup: can we make the pcs less ugly to create?
        # TODO: think about non(/empty)-prefixed and prefixed parsers in the same code ...
        # TODO: is requirement for prefixing compatible with combining parsers (particularly multiple
        # parsers of the same sort) in a modular way?  Maybe any abstraction could also take a general prefix??
        default_config_file = os.getenv("PYDPIPER_CONFIG_FILE")
        config_files = [default_config_file] if default_config_file else []

        # First, build a parser that's aware of all options
        # (will be used for help/version/error messages).
        # This must be tried _before_ the partial parsing attempts
        # in order to get correct help/version messages.
        main_parser = PydParser(default_config_files=config_files)

        for add_fn, _, _ in pcs:
            #for arg in args:
            add_fn(main_parser)
            #main_parser.add_argument(main_parser)
        # exit with helpful message if parse fails or --help/--version specified:
        main_parser.parse_args(args)

        # Next, parse each option group into a separate namespace.
        # An alternate strategy could be to use the main parser only,
        # parsing the prefixed options into prefixed destination fields
        # (of the main Namespace object) and then iterate through these,
        # unflattening the namespace.
        n = Namespace()
        for add_fn, namespace, proc in pcs:
            parser = PydParser(default_config_files=config_files)
            add_fn(parser)
            result, _rest = parser.parse_known_args(args)
            print(namespace, _rest)
            # ensure we're not clobbering an existing sub-namespace:
            # NB if one wanted to allow some fields to be added
            # to the top-level namespace, one could
            # add result to n.__dict__ if namespace is None
            # (need additional conflict checking).
            # Currently this isn't allowed as it just complicates
            # usage for little benefit.
            if namespace in n.__dict__:
                raise ValueError("Namespace field '%s' is already in use" % namespace)
            else:
                n.__dict__[namespace] = proc(result) # (apply the cast/post-processing...)
        else:
            return n
    return parser

# TODO: what about making these add...Group fns take a group
# instead of a parser as argument?

def addApplicationArgumentGroup(parser):
    """
    The arguments that all applications share:
    --pipeline-name
    --restart
    --no-restart
    --output-dir
    --create-graph
    --execute
    --no-execute
    --version
    --verbose
    --no-verbose
    files (left over arguments (0 or more is allowed)
    """
    group = parser.add_argument_group("General application options", "General options for all pydpiper applications.")
    group.add_argument("--restart", dest="restart", 
                       action="store_false", default=True,
                       help="Restart pipeline using backup files. [default = %(default)s]")
    group.add_argument("--pipeline-name", dest="pipeline_name", type=str,
                       default=time.strftime("pipeline-%d-%m-%Y-at-%H-%m-%S"),
                       help="Name of pipeline and prefix for models.")

    group.add_argument("--no-restart", dest="restart", 
                        action="store_false", help="Opposite of --restart")
    # TODO instead of prefixing all subdirectories (logs, backups, processed, ...)
    # with the pipeline name/date, we could create one identifying directory
    # and put these other directories inside
    group.add_argument("--output-dir", dest="output_directory",
                       type=str, default='',
                       help="Directory where output data and backups will be saved.")
    group.add_argument("--create-graph", dest="create_graph",
                       action="store_true", default=False,
                       help="Create a .dot file with graphical representation of pipeline relationships [default = %(default)s]")
    parser.set_defaults(execute=True)
    parser.set_defaults(verbose=False)
    group.add_argument("--execute", dest="execute",
                       action="store_true",
                       help="Actually execute the planned commands [default = %(default)s]")
    group.add_argument("--no-execute", dest="execute",
                       action="store_false",
                       help="Opposite of --execute")
    group.add_argument("--version", action="version",
                       version="%(prog)s ("+get_distribution("pydpiper").version+")", # pylint: disable=E1101
                   ) #    help="Print the version number and exit.")
    group.add_argument("--verbose", dest="verbose",
                       action="store_true",
                       help="Be verbose in what is printed to the screen [default = %(default)s]")
    group.add_argument("--no-verbose", dest="verbose",
                       action="store_false",
                       help="Opposite of --verbose [default]")
    group.add_argument("files", type=str, nargs='*', metavar='file',
                        help='Files to process')



def addExecutorArgumentGroup(parser, prefix=None):
    group = parser.add_argument_group("Executor options",
                        "Options controlling how and where the code is run.")
    group.add_argument("--uri-file", dest="urifile",
                       type=str, default=None,
                       help="Location for uri file if NameServer is not used. If not specified, default is current working directory.")
    group.add_argument("--use-ns", dest="use_ns",
                       action="store_true",
                       help="Use the Pyro NameServer to store object locations. Currently a Pyro nameserver must be started separately for this to work.")
    group.add_argument("--latency-tolerance", dest="latency_tolerance",
                       type=float, default=15.0,
                       help="Allowed grace period by which an executor may miss a heartbeat tick before being considered failed [Default = %(default)s.")
    group.add_argument("--num-executors", dest="num_exec", 
                       type=int, default=-1, 
                       help="Number of independent executors to launch. [Default = %(default)s. Code will not run without an explicit number specified.]")
    group.add_argument("--max-failed-executors", dest="max_failed_executors",
                      type=int, default=2,
                      help="Maximum number of failed executors before we stop relaunching. [Default = %(default)s]")
    # TODO: add corresponding --monitor-heartbeats
    group.add_argument("--no-monitor-heartbeats", dest="monitor_heartbeats",
                      action="store_false",
                      help="Don't assume executors have died if they don't check in with the server (NOTE: this can hang your pipeline if an executor crashes).")
    group.add_argument("--time", dest="time", 
                       type=str, default=None,
                       help="Wall time to request for each server/executor in the format hh:mm:ss. Required only if --queue-type=pbs. Current default on PBS is 48:00:00.")
    group.add_argument("--proc", dest="proc", 
                       type=int, default=1,
                       help="Number of processes per executor. Also sets max value for processor use per executor. [Default = %(default)s]")
    group.add_argument("--mem", dest="mem", 
                       type=float, default=6,
                       help="Total amount of requested memory (in GB) for all processes the executor runs. [Default = %(default)s].")
    group.add_argument("--pe", dest="pe",
                       type=str, default=None,
                       help="Name of the SGE pe, if any. [Default = %(default)s]")
    group.add_argument("--greedy", dest="greedy",
                       action="store_true",
                       help="Request the full amount of RAM specified by --mem rather than the (lesser) amount needed by runnable jobs.  Always use this if your executor is assigned a full node.")
    group.add_argument("--ppn", dest="ppn", 
                       type=int, default=8,
                       help="Number of processes per node. Used when --queue-type=pbs. [Default = %(default)s].")
    group.add_argument("--queue-name", dest="queue_name", type=str, default=None,
                       help="Name of the queue, e.g., all.q (MICe) or batch (SciNet)")
    group.add_argument("--queue-type", dest="queue_type", type=str, default=None,
                       help="""Queue type to submit jobs, i.e., "sge" or "pbs".  [Default = %(default)s]""")
    group.add_argument("--queue-opts", dest="queue_opts",
                       type=str, default="",
                       help="A string of extra arguments/flags to pass to qsub. [Default = %(default)s]")
    group.add_argument("--executor-start-delay", dest="executor_start_delay", type=int, default=180,
                       help="Seconds before starting remote executors when running the server on the grid")
    group.add_argument("--time-to-seppuku", dest="time_to_seppuku", 
                       type=int, default=1,
                       help="The number of minutes an executor is allowed to continuously sleep, i.e. wait for an available job, while active on a compute node/farm before it kills itself due to resource hogging. [Default = %(default)s]")
    group.add_argument("--time-to-accept-jobs", dest="time_to_accept_jobs", 
                       type=int,
                       help="The number of minutes after which an executor will not accept new jobs anymore. This can be useful when running executors on a batch system where other (competing) jobs run for a limited amount of time. The executors can behave in a similar way by given them a rough end time. [Default = %(default)s]")
    group.add_argument('--local', dest="local", action='store_true', help="Don't submit anything to any specified queueing system but instead run as a server/executor")
    group.add_argument("--config-file", type=str, metavar='config_file', is_config_file=True,
                       required=False, help='Config file location')
    group.add_argument("--prologue-file", type=str, metavar='file',
                       help="Location of a shell script to inline into PBS submit script to set paths, load modules, etc.")
    group.add_argument("--min-walltime", dest="min_walltime", type=int, default = 0,
            help="Min walltime (s) allowed by the queuing system [Default = %(default)s]")
    group.add_argument("--max-walltime", dest="max_walltime", type=int, default = None,
            help="Max walltime (s) allowed for jobs on the queuing system, or infinite if None [Default = %(default)s]")
    group.add_argument("--default-job-mem", dest="default_job_mem",
                       type=float, default = 1.75,
                       help="Memory (in GB) to allocate to jobs which don't make a request. [Default=%(default)s]")

def addGeneralRegistrationArgumentGroup(parser):
    group = parser.add_argument_group("General registration options",
                                      "....")
    group.add_argument("--input-space", dest="input_space",
                       choices=['native', 'lsq6', 'lsq12'], default="native", 
                       help="Option to specify space of input-files. Can be native (default), lsq6, lsq12. "
                            "Native means that there is no prior formal alignent between the input files " 
                            "yet. lsq6 means that the input files have been aligned using translations "
                            "and rotations; the code will continue with a 12 parameter alignment. lsq12 " 
                            "means that the input files are fully linearly aligned. Only non linear "
                            "registrations are performed.")
    group.add_argument("--resolution", dest="resolution", type=float,
                        help="Resolution to run the pipeline "
                        "(or determined by initial target if unspecified)")

# TODO: where should this live?
class RegistrationConf(Atom):
    input_space = Enum('native', 'lsq6', 'lsq12')
    resolution  = Instance(float)


def addStatsArgumentGroup(parser):
    group = parser.add_argument_group("Statistics options", 
                          "Options for calculating statistics.")
    default_fwhms = ['0.5','0.2','0.1']
    group.add_argument("--stats-kernels", dest="stats_kernels",
                       type=','.split, default=[0.5,0.2,0.1],
                       help="comma separated list of blurring kernels for analysis. Default is: %s" % ','.join(default_fwhms))


def addRegistrationChainArgumentGroup(parser):
    group = parser.add_argument_group("Registration chain options",
                        "Options for processing longitudinal data.")
#    addGeneralRegistrationArguments(group)
    group.add_argument("--csv-file", dest="csv_file",
                       type=str, required=True,
                       help="The spreadsheet with information about your input data. "
                            "For the registration chain you are required to have the "
                            "following columns in your csv file: \" subject_id\", "
                            "\"timepoint\", and \"filename\". Optionally you can have "
                            "a column called \"is_common\" that indicates that a scan "
                            "is to be used for the common time point registration"
                            "using a 1, and 0 otherwise.")
    group.add_argument("--common-time-point", dest="common_time_point",
                       type=int, default=None,
                       help="The time point at which the inter-subject registration will be "
                            "performed. I.e., the time point that will link the subjects together. "
                            "If you want to use the last time point from each of your input files, "
                            "(they might differ per input file) specify -1. If the common time "
                            "is not specified, the assumption is that the spreadsheet contains "
                            "the mapping using the \"is_common\" column. [Default = %(default)s]")
    group.add_argument("--common-time-point-name", dest="common_time_point_name",
                       type=str, default="common", 
                       help="Option to specify a name for the common time point. This is useful for the "
                            "creation of more readable output file names. Default is \"common\". Note "
                            "that the common time point is the one created by an iterative group-wise " 
                            "registration (inter-subject).")


core_pieces = [(addApplicationArgumentGroup, 'application'),
               (addExecutorArgumentGroup,    'execution')]

# TODO probably doesn't belong here ...
def addLSQ12ArgumentGroup(prefix):
    prefix = "" if prefix in ["", None] else (prefix + '-')
    def f(parser):
        """option group for the command line argument parser"""
        group = parser.add_argument_group("LSQ12 registration options",
                            "Options for performing a pairwise, affine registration")
        group.add_argument("--%slsq12-max-pairs" % prefix, dest="lsq12_max_pairs",
                           type=nullable_int, default=25,
                           help="Maximum number of pairs to register together ('None' implies all pairs).  [Default = %(default)s]")
        group.add_argument("--%slsq12-likefile" % prefix, dest="lsq12_likeFile",
                           type=str, default=None,
                           help="Can optionally specify a like file for resampling at the end of pairwise "
                           "alignment. Default is None, which means that the input file will be used. [Default = %(default)s]")
        group.add_argument("--%slsq12-subject-matter" % prefix, dest="lsq12_subject_matter",
                           type=str, default=None,
                           help="Can specify the subject matter for the pipeline. This will set the parameters "
                           "for the 12 parameter alignment based on the subject matter rather than the file "
                           "resolution. Currently supported option is: \"mousebrain\". [Default = %(default)s].")
        group.add_argument("--%slsq12-protocol" % prefix, dest="lsq12_protocol",
                           type=str, default=None,
                           help="Can optionally specify a registration protocol that is different from defaults. "
                           "Parameters must be specified as in the following example: \n"
                           "applications_testing/test_data/minctracc_example_linear_protocol.csv \n"
                           "[Default = %(default)s].")
        parser.add_argument_group(group)
    return f

# attempt to sensibly add/combine two prefixed lsq12 option sets (would be same for two MBMs)
#two_lsq12_parser = make_parser([(addLSQ12ArgumentGroup('second-level'),  'second-level-lsq12'),
#                                (addLSQ12ArgumentGroup('first-level'),   'first-level-lsq12')])(['--help'])
    

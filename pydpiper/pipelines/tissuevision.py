#!/usr/bin/env python3

import os
from pydpiper.core.stages import Stages, Result
from pydpiper.core.arguments import CompoundParser, AnnotatedParser, BaseParser
#TODO from pydpiper.pipelines.MBM import mbm_parser

~/pydpiper-env/bin/MICe-lab/TV/TV_stitch.py --verbose --scaleoutput 30 --keeptmp --save_positions_file positions.txt \
/projects/souris/stsatski/Salter_Microglia_Final_reconstruction/Salter_Microglia_GFP_SM1_28Feb13/mgliaGFP_sample1 \
/hpf/largeprojects/MICe/nwang/temp/Salter_stitched

def tissuevision_pipeline(options):
    output_dir = options.application.output_directory
    pipeline_name = options.application.pipeline_name
    tif_input_dir = options.tissuevision.TV_stitch.tif_input_directory
    # TODO check that the varian recon "output_dir" doesn't name a directory; or if it does, that it is correct
    # TODO check that the tif files are in "tif_input_dir"

    s = Stages()

    #############################
    # Step 1: Run TV_stitch.py
    #############################
    # varian_recon_results = s.defer(varian_recon_ge3dmice_saddle(fids=fids,
    #                                                             imgs=imgs,
    #                                                             varian_recon_options=options.saddle_recon.varian_recon,
    #                                                             output_dir=output_dir))
    tissuevision_results = s.defer()

    return Result(stages=s, output=tissuevision_result)


def _mk_tv_stitch_parser_():
    p.set_defaults(check_tiles=True)
    p.add_argument("--hello-world", dest="hello_world",
                   action="store_true",
                   help="Prints 'hello_world'")
    return p

tv_stitch_parser = AnnotatedParser(parser=BaseParser(_mk_tv_stitch_parser_(), "tissuevision"),
                                   namespace="tissuevision", cast=to_varian_recon_conf)

tissuevision_parser = CompoundParser([tv_stitch_parser])

# def _mk_crop_to_brain_parser():
#     p = ArgParser(add_help=False)
#     p.add_argument("--crop_bbox_x", dest="bbox_x",
#                    type=float, default=0,
#                    help="length of bounding box in x direction (default units in pixels)")
#     p.add_argument("--crop_bbox_y", dest="bbox_y",
#                    type=float, default=0,
#                    help="length of bounding box in y direction (default units in pixels)")
#     p.add_argument("--crop_bbox_z", dest="bbox_z",
#                    type=float, default=0,
#                    help="length of bounding box in z direction (default units in pixels)")
#     p.add_argument("--crop_buffer_z", dest="buffer_z",
#                    type=float, default=0,
#                    help="Add forced buffer in z direction (default units in pixels) (often the images sit too far forward)")
#     p.add_argument("--crop_mm_units", action="store_true",
#                    dest="mm_units", default=False,
#                    help="Units of shift are in mm instead of pixels")
#     return p

# varian_recon_parser = AnnotatedParser(parser=BaseParser(_mk_varian_recon_parser(), "varian_recon"),
    # namespace="varian_recon", cast=to_varian_recon_conf)

#saddle_recon_parser = CompoundParser([varian_recon_parser, lsq6_parser, crop_to_brain_parser])



tissuevision_application = mk_application(parsers=[tissuevision_parser], pipeline=tissuevision_pipeline)
#saddle_recon_application = mk_application(parsers=[AnnotatedParser(parser=saddle_recon_parser, namespace='saddle_recon')],
    # pipeline=saddle_recon_pipeline)

if __name__ == "__main__":
    tissuevision_application()
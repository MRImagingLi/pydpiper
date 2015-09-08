from configargparse import ArgParser
import time
import pkg_resources
import logging
import networkx as nx
import sys
import os

from pydpiper.execution.pipeline import Pipeline, pipelineDaemon
from pydpiper.execution.queueing import runOnQueueingSystem
from pydpiper.execution.file_handling import makedirsIgnoreExisting
from pydpiper.execution.pipeline_executor import addExecutorArgumentGroup, ensure_exec_specified
from pydpiper.core.util import output_directories

from   atom.api import Atom, Bool
import atom.api as atom

PYDPIPER_VERSION = pkg_resources.get_distribution("pydpiper").version # pylint: disable=E1101

logger = logging.getLogger(__name__)

class ExecutionOptions(Atom):
    use_backup_files = Bool(True)
    create_graph     = Bool(False)
    execute          = Bool(True)
    # ... TODO: put remainder of executor args, ..., here?

def addApplicationArgumentGroup(parser):
    group = parser.add_argument_group("General application options", "General options for all pydpiper applications.")
    group.add_argument("--restart", dest="restart", 
                               action="store_false", default=True,
                               help="Restart pipeline using backup files. [default = %(default)s]")
    group.add_argument("--no-restart", dest="restart", 
                               action="store_false", help="Opposite of --restart")
    # TODO: instead of prefixing all subdirectories (logs, backups, processed, ...)
    # with the pipeline name/date, we could create one identifying directory
    # and put these other directories inside
    group.add_argument("--output-dir", dest="output_directory",
                               type=str, default=None,
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
    group.add_argument("--version", action='version', version='%(prog)s %s' % PYDPIPER_VERSION)
    group.add_argument("--verbose", dest="verbose",
                               action="store_true",
                               help="Be verbose in what is printed to the screen [default = %(default)s]")
    group.add_argument("--no-verbose", dest="verbose",
                               action="store_false",
                               help="Opposite of --verbose [default]")
    group.add_argument("files", type=str, nargs='*', metavar='file',
                        help='Files to process')

# Some sneakiness... Using the following lines, it's possible
# to add an epilog to the parser that is written to screen
# verbatim. That way in the help file you can show an example
# of what an lsq6/nlin protocol should look like.
class MyParser(ArgParser):
    def format_epilog(self, formatter):
        if not self.epilog:
            self.epilog = ""
        return self.epilog

def create_parser():
    default_config_file = os.getenv("PYDPIPER_CONFIG_FILE")
    files = [default_config_file] if default_config_file is not None else []
    parser = MyParser(default_config_files=files)
    addExecutorArgumentGroup(parser)
    addApplicationArgumentGroup(parser)
    return parser

#TODO: change this to ...(static_pipeline, options)?
def execute(stages, options):
    """Basically just looks at the arguments and exits if `--no-execute` is specified,
    otherwise dispatch on backend type."""



    # TODO: logger.info('Constructing pipeline...')
    pipeline = Pipeline(stages=stages, options=options)

    # TODO: print/log version

    if options.create_graph:
        logger.debug("Writing dot file...")
        nx.write_dot(pipeline.G, str(options.pipeline_name) + "_labeled-tree.dot")
        logger.debug("Done.")

    if not options.execute:
        print("Not executing the command (--no-execute is specified).\nDone.")
        return

    reconstruct_command(options)
    
    # TODO: should create_directories be added as a method to Pipeline?
    # TODO: move calls to create_directories into execution functions
    create_directories(stages)

    execution_proc = backend(options)
    execution_proc(pipeline, options)

def backend(options):
    return normal_execute if options.local else execution_backends[options.queue_type]

def create_directories(stages):
    dirs = output_directories(stages)
    # TODO: should provide option to turn this off if already created
    for d in dirs:
        try:
            os.makedirs(d)
        except OSError as e:
            # FIXME check it's from the directory already existing
            pass

# The old AbstractApplication class has been removed due to its API being non-obvious.  Instead,
# we currently provide an `execute` function and some helper functions for command-line parsing.
# In the future, we could also provide higher-order functions which invert control again, although
# with a clearer interface than AbstractApplication.  This would be nice since the user wouldn't have
# to remember to add the executor option group themselves, for example, but would have to be done tastefully.

def normal_execute(pipeline, options):
    # FIXME this is a trivial function; inline pipelineDaemon here
    #pipelineDaemon runs pipeline, launches Pyro client/server and executors (if specified)
    logger.info("Starting pipeline daemon...")
    # TODO: make a flag to disable this in case already created, wish to create later, etc.
    create_directories(pipeline.stages) # TODO: or whatever
    pipelineDaemon(pipeline, options, sys.argv[0])
    logger.info("Server has stopped.  Quitting...")

def grid_only_execute(pipeline, options):
    #    if pbs_submit:
    roq = runOnQueueingSystem(options, sys.argv)
    roq.createAndSubmitPbsScripts()
    # TODO: make the local server create the directories (first time only) OR create them before submitting OR submit a separate stage?
    # NOTE we can't add a stage to the pipeline at this point since the pipeline doesn't support any sort of incremental recomputation ...
    logger.info("Finished submitting PBS job scripts...quitting")

execution_backends = { None : normal_execute, 'sge' : normal_execute, 'pbs' : grid_only_execute }

def reconstruct_command(options):
    # TODO: also write down the environment, contents of config files
    reconstruct = ' '.join(sys.argv)
    logger.info("Command is: " + reconstruct)
    logger.info("Command version : " + PYDPIPER_VERSION)
    fileForCommandAndVersion = options.pipeline_name + "-command-and-version-" + time.strftime("%d-%m-%Y-at-%H-%m-%S") + ".sh"
    pf = open(fileForCommandAndVersion, "w")
    pf.write("#!/usr/bin/env bash\n")
    pf.write("# Command version is: " + PYDPIPER_VERSION + "\n")
    pf.write("# Command was: \n")
    pf.write(reconstruct + '\n')
    pf.close()
 
class AbstractApplication(object):
    # FIXME check that only one server is running with a given output directory
    def _setup_directories(self):
        """Output and backup directories setup here."""
        if not self.options.output_directory:
            self.outputDir = os.getcwd()
        else:
            self.outputDir = makedirsIgnoreExisting(self.options.output_directory)
        self.pipeline.setBackupFileLocation(self.outputDir)

       
    def start(self):
        # Check to make sure some executors have been specified if we are 
        # actually going to run:
        if self.options.execute:
            ensure_exec_specified(self.options.num_exec)
             
        self._setup_pipeline(self.options)
        self._setup_directories()
        
        if (self.options.execute and not pbs_submit) or self.options.create_graph:
            self.pipeline.printStages(self.options.pipeline_name)
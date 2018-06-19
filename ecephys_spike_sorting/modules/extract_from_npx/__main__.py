from argschema import ArgSchemaParser
import os
import logging
import subprocess
import time

import numpy as np

from _schemas import InputParameters, OutputParameters


def run_npx_extractor(args):

    # load lfp band data
    
    free_space = os.statvfs(args['output_file_path'])
    
    filesize = os.path.getsize(args['npx_file_location'])
    
    assert(free_space > filesize)
    
    logging.info('Running NPX Extractor')
    
    start = time.time()
    subprocess.check_call(args['executable_file'], args['npx_file_location'], args['output_file_path'])
    execution_time = time.time() - start
    
    return {"execution_time" : execution_time} # output manifest


def main():

    """Main entry point:"""
    mod = ArgSchemaParser(schema_type=InputParameters,
                          output_schema_type=OutputParameters)

    output = run_npx_extractor(mod.args)

    output.update({"input_parameters": mod.args})
    if "output_json" in mod.args:
        mod.output(output, indent=2)
    else:
        print(mod.get_output_json(output))


if __name__ == "__main__":
    main()
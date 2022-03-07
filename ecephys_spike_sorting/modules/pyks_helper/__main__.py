
from argschema import ArgSchemaParser
import os
import time
import shutil

import numpy as np



from pathlib import Path

from scipy.signal import butter, filtfilt, medfilt

from ibllib.io import spikeglx
from ibllib.ephys import spikes, neuropixel
from pykilosort import add_default_handler, run, Bunch, __version__
from pykilosort.params import KilosortParams
from pykilosort.janelia import run_spike_sorting_janelia


from ...common.SGLXMetaToCoords import MetaToCoords
from ...common.utils import read_probe_json, get_repo_commit_date_and_hash, rms

def run_pyks(args):

    print('ecephys spike sorting: pyks helper module')

    input_file = args['ephys_params']['ap_band_file']
    input_file_forward_slash = input_file.replace('\\','/')

    output_dir = args['directories']['kilosort_output_directory']
    output_dir_forward_slash = output_dir.replace('\\','/')
    
    mask = get_noise_channels(args['ephys_params']['ap_band_file'],
                              args['ephys_params']['num_channels'],
                              args['ephys_params']['sample_rate'],
                              args['ephys_params']['bit_volts'])
     
    

    # Asuuming SpikeGLX data, will get values for Probe Bunch from metadata
    # Also save matlab KS2 chanMap for use by C_Waves helper (to make clus_Table.npy)
    # If noise channels are detected, coonected[channel index] = 0

    # metadata file must be in the same directory as the ap_band_file
    # resulting chanmap is copied to the matlab home directory, and will 
    # overwrite any existing 'chanMap.mat'
    metaName, binExt = os.path.splitext(args['ephys_params']['ap_band_file'])
    metaFullPath = Path(metaName + '.meta')

    destFullPath = os.path.join(args['kilosort_helper_params']['matlab_home_directory'], 'chanMap.mat')
    MaskChannels = np.where(mask == False)[0]      
    xCoord, yCoord, shankInd, connected = MetaToCoords( metaFullPath=metaFullPath, outType=1, badChan=MaskChannels, destFullPath=destFullPath)


    start = time.time()
    
    
    probe = Bunch()
    probe.NchanTOT = args['ephys_params']['num_channels']   #all channels in file
    neural_channels = connected.shape[0]   
    probe.chanMap = np.arange(neural_channels)
    probe.xc = xCoord
    probe.yc = yCoord
    probe.kcoords = shankInd    # unlike MATLAB, use zero-based index for shank and channel 
    
    params = KilosortParams()   # pyks2 function that sets all params to defaults
    params.preprocessing_function = 'kilosort2'
    params.ks2_mode = False
    params.deterministic_mode = False  #note that stable_mode is separate, as in MATLAB
    params.perform_drift_registration = True
    params.car = False
    params.fshigh = None    # set to 'None' to skip all filtering
    params.probe = probe
    params.seed = 42
    # params = {k: dict(params)[k] for k in sorted(dict(params))}
    print ('stable_mode:' + repr(params.stable_mode))
    print ('deterministic_mode:' + repr(params.deterministic_mode))

    pyks2_params = dict(params)
            
    run_spike_sorting_janelia(bin_file = args['ephys_params']['ap_band_file'], 
                              scratch_dir=None, 
                              delete=True, 
                              neuropixel_version=1,         #not used when params is not None
                              ks_output_dir=output_dir, 
                              alf_path=None, 
                              log_level='INFO', 
                              params=pyks2_params)
    
    # set dat_path in params.py
    #    if the user has not requested a copy of the procecess temp_wh file
    # set to relative path to the original input binary; set the number of channels
    # to number of channels in the input
    #    if the user has rquested a copy of the processed temp_wh, copy that file
    # to the input directory and set dat_path to point to it. Set the number of 
    # channls in the processed file
    dat_dir, dat_name = os.path.split(input_file)
    
    copy_fproc = args['kilosort_helper_params']['kilosort2_params']['copy_fproc']
  
    if copy_fproc:
        fproc_path_str = args['kilosort_helper_params']['kilosort2_params']['fproc']
        # trim quotes off string sent to matlab
        fproc_path = fproc_path_str[1:len(fproc_path_str)-1]
        fp_dir, fp_name = os.path.split(fproc_path)
        # make a new name for the processed file based on the original
        # binary and metadata files
        fp_save_name = metaName + '_ksproc.bin'
        shutil.copy(fproc_path, os.path.join(dat_dir, fp_save_name))
        cm_path = os.path.join(output_dir, 'channel_map.npy')
        cm = np.load(cm_path)
        chan_phy_binary = cm.size
        fix_phy_params(output_dir, dat_dir, fp_save_name, chan_phy_binary, args['ephys_params']['sample_rate'])
    else:
        chan_phy_binary = args['ephys_params']['num_channels']
        fix_phy_params(output_dir, dat_dir, dat_name, chan_phy_binary, args['ephys_params']['sample_rate'])                

    # make a copy of the channel map to the data directory
    # named according to the binary and meta file
    # alredy have path to chanMap = destFullPath
    cm_save_name = metaName + '_chanMap.mat'
    shutil.copy(destFullPath, os.path.join(dat_dir, cm_save_name))

    if args['kilosort_helper_params']['ks_make_copy']:
        # get the kilsort output directory name
        pPath, phyName = os.path.split(output_dir)
        # build a name for the copy
        copy_dir = os.path.join(pPath, phyName + '_orig')
        # check for whether the directory is already there; if so, delete it
        if os.path.exists(copy_dir):
            shutil.rmtree(copy_dir)
        # make a copy of output_dir
        shutil.copytree(output_dir, copy_dir)

    execution_time = time.time() - start

    print('kilsort run time: ' + str(np.around(execution_time, 2)) + ' seconds')
    print()
    
    # Don't call getSortResults until after any postprocessing
    # but get useful characteristics of ksort output right now
    spkTemplate = np.load(os.path.join(output_dir,'spike_templates.npy'))
    nTemplate = np.unique(spkTemplate).size
    nTot = spkTemplate.size
       
    return {"execution_time" : execution_time,
            "mask_channels" : np.where(mask == False)[0],
            "nTemplate" : nTemplate,
            "nTot" : nTot } # output manifest

def get_noise_channels(raw_data_file, num_channels, sample_rate, bit_volts, noise_threshold=20):

    noise_delay = 5            #in seconds
    noise_interval = 10         #in seconds
    
    raw_data = np.memmap(raw_data_file, dtype='int16')
    
    num_samples = int(raw_data.size/num_channels)
      
    data = np.reshape(raw_data, (num_samples, num_channels))
   
    start_index = int(noise_delay * sample_rate)
    end_index = int((noise_delay + noise_interval) * sample_rate)
    
    if end_index > num_samples:
        print('noise interval larger than total number of samples')
        end_index = num_samples
        
    uplim = 10000/(sample_rate/2);
    if uplim >= 1:
        uplim = 0.99;
    
    b, a = butter(3, [10/(sample_rate/2), uplim], btype='band')

    D = data[start_index:end_index, :] * bit_volts
    
    D_filt = np.zeros(D.shape)  # datatype set by D

    for i in range(D.shape[1]):
        D_filt[:,i] = filtfilt(b, a, D[:,i])

    rms_values = np.apply_along_axis(rms, axis=0, arr=D_filt)

    above_median = rms_values - medfilt(rms_values,11)
    
    print('number of noise channels: ' + repr(sum(above_median > noise_threshold)))

    return above_median < noise_threshold

def fix_phy_params(output_dir, dat_path, dat_name, chan_phy_binary, sample_rate):

    # write a new params.py file. 
    # dat_path will be set to a relative path from output_dir to
    # dat_path/dat_name
    # sample rate will be written out to sufficient digits to be used
    
    shutil.copy(os.path.join(output_dir,'params.py'), os.path.join(output_dir,'old_params.py'))
    
    relPath = os.path.relpath(dat_path, output_dir)
    new_path = os.path.join(relPath, dat_name)
    new_path = new_path.replace('\\','/')
    
    paramLines = list()
    
    with open(os.path.join(output_dir,'old_params.py'), 'r') as f:
        currLine = f.readline()
        
        while currLine != '':  # The EOF char is an empty string
            if 'dat_path' in currLine:
                currLine = "dat_path = '" + new_path + "'\n"
            elif 'n_channels_dat' in currLine:
                currLine = "n_channels_dat = " + repr(chan_phy_binary) + "\n"
            elif 'sample_rate' in currLine:
                currLine = (f'sample_rate = {sample_rate:.12f}\n')
            paramLines.append(currLine)           
            currLine = f.readline()
            
    with open(os.path.join(output_dir,'params.py'), 'w') as fout:
        for line in paramLines:
            fout.write(line)

def main():

    from ._schemas import InputParameters, OutputParameters

    """Main entry point:"""
    mod = ArgSchemaParser(schema_type=InputParameters,
                          output_schema_type=OutputParameters)

    output = run_pyks(mod.args)

    output.update({"input_parameters": mod.args})
    if "output_json" in mod.args:
        mod.output(output, indent=2)
    else:
        print(mod.get_output_json(output))


if __name__ == "__main__":
    main()

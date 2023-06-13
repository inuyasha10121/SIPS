import numpy as np
import param

from numba import jit, prange

from scipy.ndimage import gaussian_filter1d
from scipy.signal import cwt, ricker
from scipy.integrate import simpson

from typing import Tuple, Optional

def orient(p1, p2, p3):
    return (float(p2[1] - p1[1]) * (p3[0] - p2[0])) - (float(p2[0] - p1[0]) * (p3[1] - p2[1]))

@jit(nopython=True, parallel=True)
def faster_cwt_neighborhood(cwtarr, stride, maxima, minima, cwt_neighborhood=1):
    n_rows = int(cwtarr.size / stride)
    for i in prange(1, stride-cwt_neighborhood):
        for j in prange(1, n_rows-cwt_neighborhood):
            max_flag = True
            min_flag = True
            center = stride*j + i
            for ni in prange(-cwt_neighborhood, cwt_neighborhood+1):
                for nj in prange(-cwt_neighborhood, cwt_neighborhood+1):
                    if cwtarr[center] < cwtarr[stride*(j+nj) + (i+ni)]:
                        max_flag = False
                    if cwtarr[center] > cwtarr[stride*(j+nj) + (i+ni)]:
                        min_flag = False
            minima[center] = min_flag
            maxima[center] = max_flag

class ChromatogramMismatchError(Exception):
    pass
class ChromatogramHeaderError(Exception):
    pass
class ChromatogramTargetError(Exception):
    pass
class TargetDefinitionError(Exception):
    pass
class SequencingDataError(Exception):
    pass
class SequencingDisplayError(Exception):
    pass

def save_str_bin(input: str) -> bytes:
    """Function to convert a string to binary

    Args:
        input (str): String to be converted

    Returns:
        bytes: Bytes of data with number of characters at the start
    """
    return np.uint32(len(input)).tobytes() + bytes(input, 'utf-8')

def read_str_bin(bin_data: np.ndarray, offset: int) -> Tuple[str, int]:
    """Function to read a string from a binary file

    Args:
        bin_data (np.ndarray): Binary data to read from
        offset (int): Offset to start read from

    Returns: out_str, offset
        out_str: Read string
        offset: New offset position
    """
    nsize = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
    offset += np.dtype(np.uint32).itemsize
    out_str = bin_data[offset:offset+nsize].decode('utf-8')
    offset += nsize
    return out_str, offset

def save_arr_bin(arr: np.ndarray, dtype: np.dtype) -> bytes:
    """Function to convert a list/array to binary
    Args:
        arr: Array to be converted
        dtype: Format to store data as
        
    Returns:
        Bytes of data with number of elements at the start
    """
    if type(arr) == list:
        b = np.array(arr, dtype=dtype)
    else:
        b = arr.astype(dtype)
    return np.uint32(b.size).tobytes() + b.tobytes()

def read_arr_bin(bin_data: np.ndarray, offset: int, dtype: np.dtype) -> Tuple[np.ndarray, int]:
    """Function to read an array from a binary file
    Args:
        bin_data: Binary data to read from
        offset: Offset to start read from
        dtype: Format of stored data
        
    Returns: arr, offset
        arr: Read array
        offset: New offset position
    """
    n = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
    offset += np.dtype(np.uint32).itemsize
    if n == 0:
        return np.array([]), offset
    arr = np.frombuffer(bin_data, dtype=dtype, count=n, offset=offset)
    offset += np.dtype(dtype).itemsize * arr.size
    return arr, offset

class Chromatogram(param.Parameterized):
    time = param.Array(doc="Array containing chromatogram timepoints")
    intensity = param.Array(doc="Array containing chromatogram intensity data")
    sample_name = param.String(doc="Name of sample from instrument")
    source = param.String(doc="Source of uploaded data")
    drift_offset = param.Number(0, doc="Drift correction on time axis")
        
    sigma = param.Number(1, doc="Smoothing factor for Gaussian smoothing")
    cwt_min_scale = param.Integer(1, doc="CWT minimum scale")
    cwt_max_scale = param.Integer(60, doc="CWT maximum scale")
    cwt_neighborhood = param.Integer(1, doc="Maximum neighborhood square size for maxima/minima detection")
    friction_threshold = param.Number(0, doc="Friction value for relaxing initial peak boounds")
    rt = param.Number(0, doc="Specified target peak retention time")
    rt_tolerance = param.Number(0.2, doc="Specified target peak range")
    drop_baseline = param.Boolean(False, doc="Integrate down to baseline")
    stcurve_slope = param.Number(None, doc="Standard curve slope")
    stcurve_intercept = param.Number(None, doc="Standard curve intercept")
        
    peak_area = param.Number(None, doc="Detected peak area")
    peak_rt = param.Number(None, doc="Detected peak retention time")
    peak_bound_inds = param.List([None, None], doc="Left and right peak bound indicies")
    peak_background = param.Number(None, doc="Chromatogram background level")
    peak_height = param.Number(None, doc="Detected peak height")
    peak_snr = param.Number(None, doc="Detected peak signal-to-noise ratio")
    peak_stcurve_area = param.Number(None, doc="Standard curve corrected peak area")

    def __init__(self, time=np.array([]), intensity=np.array([]), sample_name="", source="", **params):
        super().__init__(**params)
        self.time = time
        self.intensity = intensity
        self.sample_name = sample_name
        self.source = source

    def get_tree(self, level=0):
        ret_str = f"{'    '*level}|--Sample Name: {self.sample_name}\n"
        ret_str += f"{'    '*level}|--Source: {self.source}\n"
        ret_str += f"{'    '*level}|--Time: Array({self.time.size})\n"
        ret_str += f"{'    '*level}|--Intensity: Array({self.intensity.size})\n"
        return ret_str
    
    #Peak processing based on https://arxiv.org/pdf/2101.08841.pdf
    def set_processing_parameters(self, 
        rt: float, rt_tolerance: float, initial_left_bound: float, initial_right_bound: float, sigma: float, cwt_min_scale: int, cwt_max_scale: int, 
        cwt_neighborhood: int, friction_threshold: float, drop_baseline: bool,
        stcurve_slope: Optional[float]=None, stcurve_intercept: Optional[float]=None
    ) -> None:
        self.rt = rt
        self.rt_tolerance = rt_tolerance
        self.peak_bound_inds = [np.argmin(np.abs(initial_left_bound - self.time + self.drift_offset)), np.argmin(np.abs(initial_right_bound - self.time + self.drift_offset))]
        self.sigma = sigma
        self.cwt_min_scale = cwt_min_scale
        self.cwt_max_scale = cwt_max_scale
        self.cwt_neighborhood = cwt_neighborhood
        self.friction_threshold = friction_threshold
        self.drop_baseline = drop_baseline
        self.stcurve_slope = stcurve_slope
        self.stcurve_intercept = stcurve_intercept

        
    def gaussian_smoothing(self) -> np.ndarray:
        return gaussian_filter1d(self.intensity, self.sigma)
    
    def second_deriv(self, smoothed_chromatogram: np.ndarray) -> np.ndarray:
         return np.gradient(np.gradient(smoothed_chromatogram))
        
    def cwt_generation(self, second_deriv: np.ndarray) -> np.ndarray:
        #TODO: Eventually, we should limit this analysis to a range close to our peak bounds, but need more testing first before comitting to this and also need to work out display bugs
        return cwt(-second_deriv, ricker, np.arange(self.cwt_min_scale, self.cwt_max_scale))
    
    def cwt_analysis(self, cwtmatr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        cwtarr = cwtmatr.flatten()
        maxima = np.zeros(cwtarr.size, dtype=bool)
        minima = np.zeros(cwtarr.size, dtype=bool)
        faster_cwt_neighborhood(cwtarr, cwtmatr.shape[1], maxima, minima, self.cwt_neighborhood)
        
        maxima = maxima.reshape(cwtmatr.shape)
        minima = minima.reshape(cwtmatr.shape)
        maxima_inds = np.array(np.where(maxima)).T[::-1] #[Scale, Time index]
        minima_inds = np.array(np.where(minima)).T#[Scale, Time index]
        #Remove any maxima that do not have a minima flanking on one side
        maxima_inds = maxima_inds[(np.min(minima_inds[:,1]) < maxima_inds[:,1]) &
                                      (maxima_inds[:,1] < np.max(minima_inds[:,1]))]
        return minima_inds, maxima_inds
    
    def score_stationary_points(self, cwtmatr: np.ndarray, indices: np.ndarray, target_time: float, target_tolerance: float) -> int:
        fitness_values = cwtmatr[indices[:,0], indices[:,1]] * (
            1 - (((self.time + self.drift_offset)[indices[:,1]] - target_time) / target_tolerance)**2)
        return fitness_values.argmax()
    
    def get_initial_peak_bounds(self, cwtmatr: np.ndarray, minima_inds: np.ndarray) -> None:
        partial_span = ((self.time[-1] - self.time[0]) / self.time.size) * (self.peak_bound_inds[1] - self.peak_bound_inds[0]) / 3
        self.peak_bound_inds = [
            minima_inds[self.score_stationary_points(-cwtmatr, minima_inds, self.rt - partial_span, partial_span),1],
            minima_inds[self.score_stationary_points(-cwtmatr, minima_inds, self.rt + partial_span, partial_span),1],
        ]
        #all_inds = np.vstack((maxima_inds, minima_inds))
        #max_range = np.max(all_inds, axis=0)
        #min_range = np.min(all_inds, axis=0)
        #denom = max_range - min_range
        #norm_maxima_inds = (maxima_inds - min_range) / denom
        #norm_minima_inds = (minima_inds - min_range) / denom
        #
        ##Get distances of minima to the best peak
        #dists = np.sqrt(np.sum((norm_maxima_inds[best_index] - norm_minima_inds)**2, axis=1))
        ##Determine closest minima flanking the peak maximum
        #left_inds = np.where(minima_inds[:,1] < maxima_inds[best_index,1])[0]
        #right_inds = np.where(minima_inds[:,1] > maxima_inds[best_index,1])[0]
        #closest_left_ind = left_inds[dists[left_inds].argmin()]
        #closest_right_ind = right_inds[dists[right_inds].argmin()]
        #self.peak_bound_inds = [minima_inds[closest_left_ind][1], minima_inds[closest_right_ind][1]]
    
    def friction_boundary_correction(self, smoothed_chromatogram: np.ndarray) -> None:
        #TODO: We should probably use the norm range of the peak, instead of the full spectrum
        norm_t = (np.max(smoothed_chromatogram) - np.min(smoothed_chromatogram)) * self.friction_threshold
        size_y = smoothed_chromatogram.size
        while (self.peak_bound_inds[1] < size_y - 1) and ((smoothed_chromatogram[self.peak_bound_inds[1]] - smoothed_chromatogram[self.peak_bound_inds[1]+1]) > norm_t):
            self.peak_bound_inds[1] += 1
        while (self.peak_bound_inds[0] > 0) and ((smoothed_chromatogram[self.peak_bound_inds[0]] - smoothed_chromatogram[self.peak_bound_inds[0]-1]) > norm_t):
            self.peak_bound_inds[0] -= 1
    
    def partial_convex_hull_boundary_correction(self) -> None:
        selected_chromatogram_arr = np.vstack((self.time + self.drift_offset, self.intensity)).T
        peak_points = np.arange(self.peak_bound_inds[0], self.peak_bound_inds[1])
        W = []
        W.append(peak_points[0])
        W.append(peak_points[1])
        for j in range(2, len(peak_points)):
            while (len(W) >= 2) and (orient(selected_chromatogram_arr[peak_points[j]], 
                                selected_chromatogram_arr[W[-1]], selected_chromatogram_arr[W[-2]]) <= 0):
                W.pop()
            W.append(peak_points[j])
        self.peak_bound_inds[0] = np.min(W)
        self.peak_bound_inds[1] = np.max(W)
    
    def get_peak_characteristics(self, smoothed_chromatogram: np.ndarray, maxima_inds: np.ndarray, best_index: int) -> None:
        selected_chromatogram_arr = np.vstack((self.time + self.drift_offset, self.intensity)).T
        peak_points = selected_chromatogram_arr[self.peak_bound_inds[0]:self.peak_bound_inds[1]]
        
        peak_rt_index = maxima_inds[best_index,1]
        self.peak_rt = self.time[peak_rt_index] + self.drift_offset
        
        if self.drop_baseline:
            self.peak_area = simpson(peak_points[:,1], peak_points[:,0])
            self.peak_slope = 0 
            self.peak_background = 0
            self.peak_height = self.intensity[peak_rt_index]
        else:
            self.peak_area = 0.5*np.abs(np.sum(peak_points[:-1,0] * peak_points[1:,1]) + (peak_points[-1,0] * peak_points[0,1]) -np.sum(peak_points[1:,0] * peak_points[:-1,1]) - (peak_points[0,0] * peak_points[-1,1]))
            self.peak_slope = (selected_chromatogram_arr[self.peak_bound_inds[1],1] - selected_chromatogram_arr[self.peak_bound_inds[0],1]) / (selected_chromatogram_arr[self.peak_bound_inds[1],0] - selected_chromatogram_arr[self.peak_bound_inds[0],0])
            self.peak_background = selected_chromatogram_arr[self.peak_bound_inds[0],1] + ((selected_chromatogram_arr[peak_rt_index,0] - selected_chromatogram_arr[self.peak_bound_inds[0],0]) * self.peak_slope)
            self.peak_height = selected_chromatogram_arr[peak_rt_index,1] - self.peak_background
        
        #Signal-to-noise ratio
        chromatogram_noise = self.intensity - smoothed_chromatogram

        average_noise = np.average(chromatogram_noise)
        #In the paper, they do the inverse of this (Std/height), which confuses the hell out of me...
        self.peak_snr = (2 * self.peak_height) / np.sqrt((1/(chromatogram_noise.size - 1)) * np.sum((chromatogram_noise - average_noise)**2))
        
    def process_peak(self):
        smoothed_chromatogram = self.gaussian_smoothing()
        second_deriv = self.second_deriv(smoothed_chromatogram)
        cwtmatr = self.cwt_generation(second_deriv)
        minima_inds, maxima_inds = self.cwt_analysis(cwtmatr)
        best_index = self.score_stationary_points(cwtmatr, maxima_inds, self.rt, self.rt_tolerance)
        self.get_initial_peak_bounds(cwtmatr, minima_inds)
        self.friction_boundary_correction(smoothed_chromatogram)
        self.partial_convex_hull_boundary_correction()
        self.rt = self.time[maxima_inds[best_index,1]] + self.drift_offset
        self.get_peak_characteristics(smoothed_chromatogram, maxima_inds, best_index)
        if (self.stcurve_slope != None) and (self.stcurve_intercept != None):
            self.peak_stcurve_area = (self.stcurve_slope * self.peak_area) + self.stcurve_intercept
        else:
            self.peak_stcurve_area = None
        
    def save_binary(self, bin_data: bytes) -> bytes:
        bin_data += (
            np.array([self.cwt_min_scale, self.cwt_max_scale, self.cwt_neighborhood, self.drop_baseline, 
                self.peak_bound_inds[0], self.peak_bound_inds[1]], dtype=np.int32).tobytes() + 
            np.array([self.sigma, self.friction_threshold, self.rt, self.rt_tolerance, 
                self.peak_area, self.peak_rt, self.peak_background, self.peak_height, self.peak_snr], dtype=np.float32).tobytes() +
            save_arr_bin(self.time, np.float32) + save_arr_bin(self.intensity, np.float32)
        )
        return bin_data
    
    def load_binary(self, bin_data: bytes, offset: int) -> int:
        self.cwt_min_scale, self.cwt_max_scale, self.cwt_neighborhood, db, self.peak_bound_inds[0], self.peak_bound_inds[1] = [int(x) for x in np.frombuffer(bin_data, dtype=np.int32, count=6, offset=offset)]
        self.drop_baseline = bool(db)
        offset += 6 * np.dtype(np.int32).itemsize
        self.sigma, self.friction_threshold, self.rt, self.rt_tolerance, self.peak_area, self.peak_rt, self.peak_background, self.peak_height, self.peak_snr = np.frombuffer(bin_data, dtype=np.float32, count=9, offset=offset)
        offset += 9 * np.dtype(np.float32).itemsize
        self.time, offset = read_arr_bin(bin_data, offset, np.float32)
        self.intensity, offset = read_arr_bin(bin_data, offset, np.float32)
        return offset
    
    #def get_json(self):
    #    return json.loads(self.param.serialize_parameters([
    #        "time", "intensity", "sigma", "cwt_min_scale", "cwt_max_scale", "cwt_neighborhood", "friction_threshold", "rt", 
    #        "rt_tolerance", "drop_baseline", "peak_area", "peak_rt", "peak_bound_inds", "peak_background", "peak_height", "peak_snr"
    #    ]))

class Sequencing(param.Parameterized):
    forward_alignment = param.Array(np.array([]), doc="Forward read alignment")
    forward_abi_traces = param.Array(np.array([]), doc="Forward read abi signal data in A,T,C,G order")
    reverse_alignment = param.Array(np.array([]), doc="Reverse read alignment")
    reverse_abi_traces = param.Array(np.array([]), doc="Reverse read abi signal data for A,T,C,G order")
    
    def __init__(self, **params):
        super().__init__(**params)
    
    def save_binary(self, bin_data: bytes) -> bytes:
        bin_data += (
            save_arr_bin(self.forward_alignment, np.uint8) + 
            save_arr_bin(self.forward_abi_trace, np.int16) + 
            save_arr_bin(self.reverse_alignment, np.uint8) + 
            save_arr_bin(self.reverse_abi_trace, np.int16)
        )
        return bin_data
    
    def load_binary(self, bin_data: bytes, offset: int) -> int:
        self.forward_alignment, offset = read_arr_bin(bin_data, offset, np.uint8)
        self.forward_abi_trace, offset = read_arr_bin(bin_data, offset, np.int16)
        self.reverse_alignment, offset = read_arr_bin(bin_data, offset, np.uint8)
        self.reverse_abi_trace, offset = read_arr_bin(bin_data, offset, np.int16)
        return offset
    
    #def get_json(self):
    #    return json.loads(self.param.serialize_parameters())
    
class Well(param.Parameterized):
    chromatograms = param.Dict({}, doc="Chromatograms of targets")
    sequencing = param.ClassSelector(class_=Sequencing, default=None)
    
    def __init__(self, **params) -> None:
        super().__init__(**params)
    def __getitem__(self, key: str) -> Chromatogram:
        return self.chromatograms[key]
    def __setitem__(self, key: str, value: Chromatogram):
        if type(value) != Chromatogram:
            raise ValueError("Only Chromatogram objects are assignable this way")
        self.chromatograms[key] = value
    def __delitem__(self, key: str):
        del self.chromatograms[key]
    def __contains__(self, key: str):
        return key in self.chromatograms
    def __len__(self):
        return len(self.chromatograms)
    def __iter__(self):
        return iter(self.chromatograms)
    
    def get_tree(self, level=0):
        ret_str = ""
        for compound in self.chromatograms:
            ret_str += f"{'    '*level}|--{compound}\n{self.chromatograms[compound].get_tree(level+1)}"
        return ret_str
        
    def add_chromatogram(self, target_compound: str, time: np.ndarray, intensity: np.ndarray, sample_name="", source=""):
        self.chromatograms[target_compound] = Chromatogram(time, intensity, sample_name, source)

    def remove_chromatogram(self, target_compound: str):
        if target_compound in self.chromatograms:
            del self.chromatograms[target_compound]
        else:
            raise ValueError(f"{target_compound} not found in chromatograms")
    
    def save_binary(self, bin_data: bytes) -> bytes:
        chrom_names = list(self.chromatograms)
        n_chroms = len(chrom_names)
        bin_data += np.uint32(n_chroms).tobytes()
        for i in range(n_chroms):
            bkey = bytes(chrom_names[i], 'utf-8')
            bin_data += np.uint32(len(bkey)).tobytes()
            bin_data += bkey
            bin_data = self.chromatograms[chrom_names[i]].save_binary(bin_data)
        if self.sequencing:
            bin_data += np.uint8(1).tobytes()
            bin_data = self.sequencing.save_binary(bin_data)
        else:
            bin_data += np.uint8(0).tobytes()
        return bin_data
    
    def load_binary(self, bin_data: bytes, offset: int) -> int:
        n_chroms = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
        offset += np.dtype(np.uint32).itemsize
        for i in range(n_chroms):
            nsize = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
            offset += np.dtype(np.uint32).itemsize
            key = bin_data[offset:offset+nsize].decode('utf-8')
            offset += nsize
            self.chromatograms[key] = Chromatogram()
            offset = self.chromatograms[key].load_binary(bin_data, offset)
        has_sequencing = bool(np.frombuffer(bin_data, dtype=np.uint8, count=1, offset=offset)[0])
        offset += np.dtype(np.uint8).itemsize
        if has_sequencing:
            self.sequencing = Sequencing()
            offset = self.sequence.load_binary(bin_data, offset)
        return offset
    
    #def get_json(self):
    #    json_params = json.loads('{}')
    #    if self.sequencing != None:
    #        json_params['sequencing'] = self.sequencing.get_json()
    #    json_params['chromatograms'] = {}
    #    for chrom in self.chromatograms:
    #        json_params['chromatograms'][chrom] = self.chromatograms[chrom].get_json()
    #    return json_params

class Plate(param.Parameterized):
    wells = param.Dict({}, doc="Stored wells")
    compounds = param.List([], doc="All compounds found during data entry")
    
    parent_alignment = param.Array(np.array([]), doc="Alignment for all wells of the parent DNA sequence")
    
    def __init__(self, **params):
        super().__init__(**params)
    def __getitem__(self, key: str) -> Well:
        return self.wells[key]
    def __setitem__(self, key: str, value: Well):
        if type(value) != Well:
            raise ValueError("Only Well objects are assignable this way")
        self.wells[key] = value
    def __delitem__(self, key: str):
        del self.wells[key]
    def __contains__(self, key: str):
        return key in self.wells
    def __len__(self):
        return len(self.wells)
    def __iter__(self):
        return iter(self.wells)

    def get_tree(self, level=0):
        ret_str = ""
        for well in self.wells:
            ret_str += f"{'    '*level}|--{well}\n{self.wells[well].get_tree(level+1)}"
        return ret_str
    
    def add_well(self, well_id: str):
        self.wells[well_id] = Well()

    def remove_well(self, well_id: str):
        if well_id in self.wells:
            del self.wells[well_id]
        else:
            raise ValueError(f"Well {well_id} not found in plate")

    def save_binary(self, bin_data: bytes) -> bytes:
        bin_data += save_arr_bin(self.parent_alignment, np.uint8)
        
        well_names = list(self.wells)
        n_wells = len(well_names)
        bin_data += np.uint32(n_wells).tobytes()
        for i in range(n_wells):
            bkey = bytes(well_names[i], 'utf-8')
            bin_data += np.uint32(len(bkey)).tobytes()
            bin_data += bkey
            bin_data = self.wells[well_names[i]].save_binary(bin_data)
        return bin_data
    
    def load_binary(self, bin_data: bytes, offset: int) -> int:
        self.parent_alignment, offset = read_arr_bin(bin_data, offset, dtype=np.uint8)
        
        n_wells = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
        offset += np.dtype(np.uint32).itemsize
        for i in range(n_wells):
            nsize = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
            offset += np.dtype(np.uint32).itemsize
            key = bin_data[offset:offset+nsize].decode('utf-8')
            offset += nsize
            self.wells[key] = Well()
            offset = self.wells[key].load_binary(bin_data, offset)
        return offset
    
    #def get_json(self):
    #    json_params = json.loads('{}')
    #    json_params['wells'] = {}
    #    for well in self.wells:
    #        json_params['wells'][well] = self.wells[well].get_json()
    #    return json_params

class Library(param.Parameterized):
    plates = param.Dict({}, doc="Stored plates")
    compounds = param.List([], doc="All compounds found during data entry")
    
    def __init__(self, **params):
        super().__init__(**params)
    def __getitem__(self, key: str) -> Plate:
        return self.plates[key]
    def __setitem__(self, key: str, value: Plate):
        if type(value) != Plate:
            raise ValueError("Only Plate objects are assignable this way")
        self.plates[key] = value
    def __delitem__(self, key: str):
        del self.plates[key]
    def __contains__(self, key: str):
        return key in self.plates
    def __len__(self):
        return len(self.plates)
    def __iter__(self):
        return iter(self.plates)

    def get_tree(self, level=0):
        ret_str = "Library\n"
        for plate in self.plates:
            ret_str += f"|--{plate}\n{self.plates[plate].get_tree(level+1)}"
        return ret_str
    
    def add_plate(self, plate_name: str):
        self.plates[plate_name] = Plate()

    def remove_plate(self, plate_name: str):
        if plate_name in self.plates:
            del self.plates[plate_name]
        else:
            raise ValueError(f"Plate {plate_name} not found in plates")

    def save_binary(self, file_path: str):
        bin_data = b''
        plate_names = list(self.plates)
        n_plates = len(plate_names)
        bin_data += np.uint32(n_plates).tobytes()
        for i in range(n_plates):
            bkey = bytes(plate_names[i], 'utf-8')
            bin_data += np.uint32(len(bkey)).tobytes()
            bin_data += bkey
            bin_data = self.plates[plate_names[i]].save_binary(bin_data)
        with open(file_path, 'wb') as f:
            f.write(bin_data)
    
    def load_binary(self, file_path: str):
        bin_data = None
        offset = 0
        with open(file_path, 'rb') as f:
            bin_data = f.read()
        n_plates = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
        offset += np.dtype(np.uint32).itemsize
        for i in range(n_plates):
            nsize = np.frombuffer(bin_data, dtype=np.uint32, count=1, offset=offset)[0]
            offset += np.dtype(np.uint32).itemsize
            key = bin_data[offset:offset+nsize].decode('utf-8')
            offset += nsize
            self.plates[key] = Plate()
            offset = self.plates[key].load_binary(bin_data, offset)
    
    #def get_json(self):
    #    json_params = json.loads('{}')
    #    json_params['plates'] = {}
    #    for plate in self.plates:
    #        json_params['plates'][plate] = self.plates[plate].get_json()
    #    return json_params
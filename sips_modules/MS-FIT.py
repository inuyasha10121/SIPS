import numpy as np
import pandas as pd
from io import StringIO

import param
import panel as pn

from scipy.ndimage import gaussian_filter1d
from scipy.integrate import simpson

import traceback

import holoviews as hv
from holoviews import opts
from holoviews.streams import Stream, DoubleTap, SingleTap, Selection1D

from bokeh import palettes

from .PlateClass import Library

sidebar_text = """### MS-FIT
This pane is responsible for processing and integrating chromatography data.  

* The upper plot shows an overlay of all the chromatographs of the specified compound in the plate, or any chromatographs from selected wells
* The middle plot shows a heatmap of the integrated plate peak areas.  If a well is not present, it will be gray.  If a well is selected, it will be bordered in white.
* The advanced tab allows for showing the Continuous Wavelet Transform results, as well as fine tuning of parameters (see documentation)


The workflow for processing data is as follows:

* Double click to the left and right of a peak bundle to select that region for analysis
* Change the "Smoothing" factor to create smooth gaussian peaks
* Increasing the "Friction threshold" will cause the baseline to creep up the peak.  This can avoid the baseline drifing far from the peak.
* "Drop baseline" will force the integration baseline to drop to zero.  Useful for split peaks.
* If available, standard curve conversion can be specified with a slope and intercept.
* 
"""

class module_class:
    def __init__(self, tab_id, library: Library, status_text: pn.widgets.TextInput, progress_bar: pn.widgets.Progress, debug_text: pn.widgets.TextInput):
        self.tab_id = tab_id
        self.library = library
        self.status_text = status_text
        self.progress_bar = progress_bar
        self.debug_text = debug_text
        
        self.pp_plate_selector = pn.widgets.Select(name='Plate', width=200)
        self.pp_compound_selector = pn.widgets.Select(name='Compound', width=200)
        
    def bind_tab(self, tab_set, sidebar_info):
        tab_set.append(("MS-FIT", self.pane_definition()))
        def tab_selection_callback(event):
            try:
                if event.name == "active":
                    if event.new == self.tab_id: #Info
                        sidebar_info.object = sidebar_text
                        plates = list(self.library)
                        if len(plates) > 0:
                            self.pp_plate_selector.options = plates
                        else:
                            self.pp_plate_selector.options = []
            except Exception as e:
                self.status_text.value = "tab_selection_callback" + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        tab_set.param.watch(tab_selection_callback, ['active'])

    def pane_definition(self):
        #Standard inputs and control definition
        pp_rt_input = pn.widgets.FloatInput(name='Retention Time', value=0, step=0.01, width=80)
        pp_rt_tolerance = pn.widgets.FloatInput(name='RT Tolerance', value=0.2, step=0.01, start=0.01, width=80)
        pp_left_bound = pn.widgets.FloatInput(name='Left Bound', value=0, step=0.01, width=80)
        pp_right_bound = pn.widgets.FloatInput(name='Right Bound', value=0, step=0.01, width=80)
        pp_sigma_input = pn.widgets.FloatInput(name='Smoothing Factor', value=3, step=0.1, start=1E-32, end=50, width=80)
        pp_cwt_min_scale_input = pn.widgets.IntInput(name='CWT Min Scale', value=1, start=1, end=97, width=80)
        pp_cwt_max_scale_input = pn.widgets.IntInput(name='CWT Max Scale', value=60, start=20, end=100, width=80)
        pp_cwt_neighborhood_input = pn.widgets.IntInput(name='CWT Neighborhood', value=1, start=1, end=49, width=80)
        pp_friction_input = pn.widgets.FloatInput(name='Friction Threshold', value=0.00, step=0.001, start=0.000, end=1.000, width=80)
        pp_stcurve_slope = pn.widgets.FloatInput(name='Slope', width=80)
        pp_stcurve_intercept = pn.widgets.FloatInput(name='Intercept', width=80)
        
        pp_drop_baseline_checkbox = pn.widgets.Checkbox(name="Drop Baseline", width=80)
        pp_drift_correct_selection_button = pn.widgets.Button(name='Selected', width=80, disabled=True, button_type='primary')
        pp_drift_correct_plate_button = pn.widgets.Button(name='Plate', width=80, disabled=True, button_type='primary')
        pp_clear_drift_correct_selection_button = pn.widgets.Button(name='Clear Sel.', width=80, disabled=True, button_type='danger')
        pp_clear_drift_correct_plate_button = pn.widgets.Button(name='Clear Plate', width=80, button_type='danger')
        pp_integrate_selection_button = pn.widgets.Button(name='Selected', width=80, disabled=True, button_type='primary')
        pp_integrate_plate_button = pn.widgets.Button(name='Plate', width=80, disabled=True, button_type='primary')
        pp_integrate_library_button = pn.widgets.Button(name='Library', width=80, disabled=True, button_type='primary')
        
        pp_peak_rt_display = pn.widgets.TextInput(name='Retention Time', width=100, disabled=True)
        pp_peak_area_display = pn.widgets.TextInput(name='Area', width=100, disabled=True)
        pp_peak_height_display = pn.widgets.TextInput(name='Height', width=100, disabled=True)
        pp_peak_snr_display = pn.widgets.TextInput(name='SNR', width=100, disabled=True)
        pp_peak_stcurve_area = pn.widgets.TextInput(name='St. Curve', placeholder='N/A', width=100, disabled=True)

        pp_cwt_analysis_button = pn.widgets.Button(name='CWT Analysis', button_type='primary')

        def download_data_csv_callback():
            try:
                #First, get all our compounds
                compounds = set()
                for plate in self.library:
                    for well in self.library[plate]:
                        compounds.update(set(self.library[plate][well]))
                columns = ['Plate', 'Well'] + list(compounds)
                n_columns = len(columns)
                #Harvest our data
                data = []
                for plate in self.library:
                    for well in self.library[plate]:
                        data.append(['' for _ in range(n_columns)])
                        data[-1][0] = plate
                        data[-1][1] = well
                        for compound in self.library[plate][well]:
                            data[-1][columns.index(compound)] = self.library[plate][well][compound].peak_area
                #Send a stream to the file download widget
                sio = StringIO()
                pd.DataFrame(data, columns=columns).to_csv(sio, index=False)
                sio.seek(0)
                return sio
            except Exception as e:
                self.status_text.value = "download_data_csv_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
                
        
        pp_download_csv_button = pn.widgets.FileDownload(
            callback=download_data_csv_callback, filename='library_integration_data.csv',
            width = 250, button_type='primary'
        )

        class PlateView(param.Parameterized):
            color_map = param.Parameter(default = palettes.Viridis256)
            
            well_list = param.List(item_type='str')

            def __init__(self, outer_instance, **params):
                super().__init__(**params)
                self.outer_instance = outer_instance
                #Setup plate overlay with grid
                self.grid = hv.Path(
                    [[(i, -0.5), (i, 7.5)] for i in np.arange(-0.5, 12.5)] + 
                    [[(-0.5, i), (11.5, i)] for i in np.arange(-0.5, 8.5)]
                    ).opts(line_color='k', line_width=3)
                self.plate_plot = hv.DynamicMap(self.plate_plot_dmap, streams=[Stream.define('Next')()]).opts(framewise=True)
                self.highlight_plot = hv.DynamicMap(self.highlight_dmap, streams=[Stream.define('Next')()]).opts(framewise=True)
                self.plot = (self.plate_plot * self.grid * self.highlight_plot).opts(xlabel="", ylabel="", xaxis='top', toolbar=None, default_tools=[])
                
                #Setup tap selection for wells
                tap = SingleTap(source=self.plate_plot)
                double_tap = DoubleTap(source=self.plate_plot)
                pn.bind(self.tap_select, x=tap.param.x, y=tap.param.y, watch=True)
                pn.bind(self.double_tap_clear, x=double_tap.param.x, y=double_tap.param.y, watch=True)
                
            def tap_select(self, x, y):
                plate = self.outer_instance.pp_plate_selector.value
                well = f"{chr(int(72-np.round(y, 0)))}{str(int(np.round(x, 0)+1)).zfill(2)}"
                if well in self.well_list:
                    del self.well_list[self.well_list.index(well)]
                    selection_view.overlay_plot.event()
                    selection_view.integration_statistics_plot.event()
                    self.highlight_plot.event()
                    selection_change()
                else:
                    if well in self.outer_instance.library[plate]:
                        self.well_list.append(well)
                        selection_view.overlay_plot.event()
                        selection_view.integration_statistics_plot.event()
                        self.highlight_plot.event()
                        selection_change()

            def double_tap_clear(self, x, y):
                self.well_list = []
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                self.highlight_plot.event()
                selection_change()

            def highlight_dmap(self):
                try:
                    plate_row = hv.Dimension('plate_row', range=(-0.5, 7.5))
                    plate_col = hv.Dimension('plate_col', range=(-0.5, 11.5))
                    plots = []
                    if self.well_list == []:
                        plots.append([(0,0),(0,0)])
                    else:
                        for well in self.well_list:
                            x = int(well[1:])-1.5
                            y = 72.5-ord(well[0])
                            plots.append([(x,y),(x+1,y),(x+1,y-1),(x,y-1),(x,y)])
                except Exception as e:
                    self.outer_instance.status_text.value = "highlight_dmap: " + str(e)
                    self.outer_instance.debug_text.value += traceback.format_exc() + "\n\n"
                return hv.Path(plots).opts(line_color='white', line_width=3).redim(x=plate_col, y=plate_row)

            def plate_plot_dmap(self):
                rgb_data = np.full((8, 12, 3), 127, dtype=np.uint8)
                plate_row = hv.Dimension('plate_row', range=(-0.5, 7.5))
                plate_col = hv.Dimension('plate_col', range=(-0.5, 11.5))
                try:
                    #Harvest data
                    row_cols = []
                    acts = []
                    plate_selection = self.outer_instance.pp_plate_selector.value
                    compound_selection = self.outer_instance.pp_compound_selector.value
                    if (plate_selection != "") and (compound_selection != "") and (plate_selection != None) and (compound_selection != None):
                        #Cycle through all wells present in plate
                        for well in self.outer_instance.library[plate_selection]:
                            #Make sure the compound is in the well
                            if compound_selection in self.outer_instance.library[plate_selection][well]:
                                #Check if we have actually integrated the well
                                if self.outer_instance.library[plate_selection][well][compound_selection].peak_area != None:
                                    #Store the indexing as well as the value for coloring
                                    row_cols.append((ord(well[0])-65, int(well[1:]) - 1))
                                    acts.append(self.outer_instance.library[plate_selection][well][compound_selection].peak_area)
                                else:
                                    #Set the well to white to indicate it is not integrated
                                    rgb_data[ord(well[0])-65, int(well[1:]) - 1] = [255, 255, 255]
                        #Only color if we have wells to color
                        if len(acts) > 0:
                            if len(acts) == 1:
                                #Fix single well to highest value
                                acts = np.array([255]).astype(np.uint8)
                            else:
                                #Normalize
                                acts = np.array(acts)
                                acts = np.round(255 * (acts - acts.min()) / (acts.max() - acts.min() + 1E-32), 0).astype(np.uint8)
                            #Make color grid
                            for i in range(acts.size):
                                hex_color = self.color_map[acts[i]][1:]
                                rgb_data[*row_cols[i], :] = [int(hex_color[i:i+2], 16) for i in range(0,6,2)]
                    return hv.RGB(rgb_data, bounds=((-0.5,-0.5,11.5,7.5))).opts(
                        xticks=[(i, str(i+1)) for i in range(12)],
                        yticks=[(i, chr(72-i)) for i in range(8)], 
                    ).redim(x=plate_col, y=plate_row)
                except Exception as e:
                    self.outer_instance.status_text.value = "plate_plot_dmap: " + str(e)
                    self.outer_instance.debug_text.value += traceback.format_exc() + "\n\n"
                    return hv.RGB(rgb_data, bounds=((-0.5,-0.5,11.5,7.5))).opts(
                        xticks=[(i, str(i+1)) for i in range(12)],
                        yticks=[(i, chr(72-i)) for i in range(8)], 
                    ).redim(x=plate_col, y=plate_row)
                
        plate_view = PlateView(outer_instance=self)


        #Custom tool for setting integration ranges
        class IntegrationSelection(param.Parameterized):

            selection_start = param.Number(default=None)
            selection_end = param.Number(default=None)
            selection_midpoint = param.Number(default=0)
            selection_span = param.Number(default=0)

            def __init__(self, outer_instance, **params):
                super().__init__(**params)
                self.outer_instance = outer_instance #Grab outer so we can access the Library
                #Setup overlay plot bits
                self.overlay_plot = hv.DynamicMap(self.overlay_plot_dmap, streams=[Stream.define('Next')()]).opts(framewise=True, tools=['hover'])
                self.integration_statistics_plot = hv.DynamicMap(self.integration_statistics_dmap, streams=[Stream.define('Next')()]).opts(framewise=True)

                #Setup selection plot bits
                selection_plot = hv.DynamicMap(self.selection_plot_dmap, streams=[self.param.selection_start, self.param.selection_end]).opts(framewise=True)
                tap = DoubleTap(source=selection_plot)
                pn.bind(self.double_tap_input, x=tap.param.x, watch=True)

                #Assemble full plot
                self.plot = (selection_plot * self.overlay_plot * self.integration_statistics_plot).opts(show_legend=False).opts(
                    opts.Curve(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity'),
                    opts.Area(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity'),
                    opts.VSpan(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity')
                )
                
            def overlay_plot_dmap(self):
                try:
                    plate = self.outer_instance.pp_plate_selector.value
                    compound = self.outer_instance.pp_compound_selector.value
                    self.outer_instance.status_text.value = "Establishing overlay object..."
                    plots = {}
                    #Make sure we have stuff to actually plot, or return an empty plot if not
                    if (plate == "") or (compound == "") or (plate == None) or (compound == None):
                        plots['N/A'] = hv.Curve((np.zeros(1), np.zeros(1)))
                    else:
                        self.outer_instance.status_text.value = "Generating curves..."
                        #Grab all our possible wells
                        well_list = self.outer_instance.library[plate]
                        #If we've made a selection, reduce what we are viewing to the selection
                        if plate_view.well_list != []:
                            well_list = [x for x in well_list if x in plate_view.well_list]
                        #Go through all our wells that we have requested to plot
                        for i, well in enumerate(well_list, 1):
                            #Make sure the compound is in the well
                            if compound in self.outer_instance.library[plate][well]:
                                #Get our time and smoothed chromatograph
                                x = self.outer_instance.library[plate][well][compound].time + self.outer_instance.library[plate][well][compound].drift_offset
                                y = gaussian_filter1d(self.outer_instance.library[plate][well][compound].intensity, pp_sigma_input.value)
                                #Add the chromatograph curve to our dictionary
                                plots[well] = hv.Curve((x,y))
                            self.outer_instance.progress_bar.value = int(np.round((i * 100) / len(well_list)))
                    self.outer_instance.status_text.value = f"Displaying overlay..."
                    #Display our overlaid plots
                    return hv.NdOverlay(plots)
                except Exception as e:
                    self.outer_instance.status_text.value = "overlay_plot_dmap: " + str(e)
                    self.outer_instance.debug_text.value += traceback.format_exc() + "\n\n"
                    return hv.NdOverlay({'N/A': hv.Curve((np.zeros(1), np.zeros(1)))})

            def integration_statistics_dmap(self):
                try:
                    plate = self.outer_instance.pp_plate_selector.value
                    compound = self.outer_instance.pp_compound_selector.value
                    plots = []
                    #Make sure we have stuff to actually plot, or return an empty plot if not
                    if (plate == "") or (compound == "") or (plate == None) or (compound == None) or (len(plate_view.well_list) == 0) or (len(plate_view.well_list) > 10):
                        plots = [
                            hv.Area(([0], [0], [0]), kdims='x', vdims=['y', 'y1']),
                            hv.Curve({'x': [0], 'y':[0]}),
                            hv.Curve({'x': [0], 'y': [0]})
                        ]
                    else:
                        plots = []
                        alpha_val = 1/len(plate_view.well_list)
                        for i, well in enumerate(plate_view.well_list, 1):
                            #Make sure the compound is in the well
                            if compound in self.outer_instance.library[plate][well]:
                                #Make sure the well has integration statistics to plot
                                if self.outer_instance.library[plate][well][compound].peak_area != None:
                                    #Get the time and chromatogram
                                    lr_inds = self.outer_instance.library[plate][well][compound].peak_bound_inds
                                    x = (self.outer_instance.library[plate][well][compound].time + self.outer_instance.library[plate][well][compound].drift_offset)[lr_inds[0]:lr_inds[1]]
                                    y_top = self.outer_instance.library[plate][well][compound].intensity[lr_inds[0]:lr_inds[1]]
                                    #Make our baseline
                                    slope = (y_top[-1] - y_top[0]) / (x[-1] - x[0])
                                    intercept = y_top[-1] - (slope * x[-1])
                                    baseline_y = (slope * x) + intercept
                                    #Get our height line index
                                    midpoint_ind = np.argmin(np.abs(x - self.outer_instance.library[plate][well][compound].rt))
                                    #Add our plots
                                    plots += [
                                        hv.Area((x, baseline_y, y_top), kdims='x', vdims=['y', 'y1']).opts(color='#808080', alpha=alpha_val),
                                        hv.Curve((x, baseline_y)).opts(color='#FF0000', alpha=alpha_val),
                                        hv.Curve(([x[midpoint_ind], x[midpoint_ind]], [baseline_y[midpoint_ind], y_top[midpoint_ind]])).opts(color='#FF0000', alpha=alpha_val)
                                    ]
                            self.outer_instance.progress_bar.value = int(np.round((i * 100) / len(plate_view.well_list)))
                    #Display our overlaid plots
                    return hv.Overlay(plots)
                except Exception as e:
                    self.outer_instance.status_text.value = "overlay_plot_dmap: " + str(e)
                    self.outer_instance.debug_text.value += traceback.format_exc() + "\n\n"
                    return hv.Overlay([
                            hv.Area(([0], [0], [0]), kdims='x', vdims=['y', 'y1']),
                            hv.Curve({'x': [0], 'y':[0]}),
                            hv.Curve({'x': [0], 'y': [0]})
                        ])
            
            def selection_plot_dmap(self, selection_start, selection_end):
                #Check if we have made a selection, as indicated by the presence of selection_end
                if selection_start == None:
                    x0 = 0
                    x1 = 0
                elif selection_end == None:
                    #If not, just show a line at the start of our selection
                    x0 = selection_start
                    x1 = selection_start
                else:
                    #If so, actually show the region
                    x0 = min(selection_start, selection_end)
                    x1 = max(selection_start, selection_end)
                return hv.VSpan(x0,x1)

            def double_tap_input(self, x):
                try:
                    #Check if we are completing a selection by filling in the end, or set the start if not
                    if self.selection_start == None:
                        self.selection_start = x
                    elif self.selection_end == None:
                        self.selection_end = max(x, self.selection_start)
                        self.selection_start = min(x, self.selection_start)
                        self.selection_midpoint = (self.selection_start + self.selection_end) / 2
                        self.selection_span = (np.abs(self.selection_end - self.selection_start) / 2)
                        pp_left_bound.value = self.selection_start
                        pp_right_bound.value = self.selection_end
                        pp_rt_input.value = self.selection_midpoint
                        pp_rt_tolerance.value = self.selection_span
                    else:
                        self.selection_start = x
                        self.selection_end = None
                        self.selection_midpoint = 0
                        self.selection_span = 0
                    selection_change()
                except Exception as e:
                    self.outer_instance.status_text.value = "double_tap_input: " + str(e)
                    self.outer_instance.debug_text.value += traceback.format_exc() + "\n\n"

        selection_view = IntegrationSelection(outer_instance=self)

        def cwt_analysis_dmap():
            cwtmatr = np.zeros((1,1))
            bounds = [0, 0, 1, 1]
            minima_inds = np.zeros((1,2))
            maxima_inds = np.zeros((1,2))
            minima_scores = np.zeros(1)
            maxima_scores = np.zeros(1)
            try:
                if len(plate_view.well_list) != 1:
                    self.status_text.value = "Please select only 1 well to analyze"
                elif selection_view.selection_end == None:
                    self.status_text.value = "Please ensure a peak span is set"
                else:
                    plate = self.pp_plate_selector.value
                    well = plate_view.well_list[0]
                    compound = self.pp_compound_selector.value
                    self.status_text.value = "Performing CWT analysis..."
                    #Set relevant parameters for well
                    self.library[plate][well][compound].rt = pp_rt_input.value
                    self.library[plate][well][compound].rt_tolerance = pp_rt_tolerance.value
                    self.library[plate][well][compound].sigma = pp_sigma_input.value
                    self.library[plate][well][compound].cwt_min_scale = pp_cwt_min_scale_input.value
                    self.library[plate][well][compound].cwt_max_scale = pp_cwt_max_scale_input.value
                    self.library[plate][well][compound].cwt_neighborhood = pp_cwt_neighborhood_input.value
                    self.library[plate][well][compound].peak_bound_inds = [
                        np.argmin(np.abs(pp_left_bound.value - self.library[plate][well][compound].time)), 
                        np.argmin(np.abs(pp_right_bound.value - self.library[plate][well][compound].time))
                    ]
                    #Perform CWT peak finding workflow
                    smoothed_chromatogram = self.library[plate][well][compound].gaussian_smoothing()
                    second_deriv = self.library[plate][well][compound].second_deriv(smoothed_chromatogram)
                    cwtmatr = self.library[plate][well][compound].cwt_generation(second_deriv)
                    self.status_text.value = "Finding minima/maxima in selection range..."
                    minima_inds, maxima_inds = self.library[plate][well][compound].cwt_analysis(cwtmatr)
                    best_index = self.library[plate][well][compound].score_stationary_points(cwtmatr, maxima_inds, self.library[plate][well][compound].rt, self.library[plate][well][compound].rt_tolerance)
                    print(f"BEST: {best_index}")
                    self.library[plate][well][compound].get_initial_peak_bounds(cwtmatr, minima_inds)
                    #Figure out bounds with appropriate padding
                    time_per_pixel = (self.library[plate][well][compound].time[-1] - self.library[plate][well][compound].time[0]) / cwtmatr.shape[1]
                    bounds = [
                        self.library[plate][well][compound].time[0] - (time_per_pixel/2),
                        pp_cwt_min_scale_input.value - 0.5,
                        self.library[plate][well][compound].time[-1] + (time_per_pixel/2),
                        pp_cwt_max_scale_input.value + 0.5
                    ]
                    #Score our minima and maxima to our specified points
                    maxima_scores = np.zeros(maxima_inds.shape[0])
                    maxima_scores[self.library[plate][well][compound].score_stationary_points(cwtmatr, maxima_inds, pp_rt_input.value, pp_rt_tolerance.value)] = 1
                    minima_scores = np.zeros(minima_inds.shape[0])
                    minima_scores[np.where(minima_inds[:,1] == self.library[plate][well][compound].peak_bound_inds[0])[0][0]] = 1
                    minima_scores[np.where(minima_inds[:,1] == self.library[plate][well][compound].peak_bound_inds[1])[0][0]] = 1
                    a = np.where(minima_inds[:,1] == self.library[plate][well][compound].peak_bound_inds[0])[0][0]
                    b = np.where(minima_inds[:,1] == self.library[plate][well][compound].peak_bound_inds[1])[0][0]
                    print(f"{self.library[plate][well][compound].time[minima_inds[a,1]]}\t{self.library[plate][well][compound].time[minima_inds[b,1]]}")

                    #Map minima and maxima indicies to time values
                    minima_inds = minima_inds.astype(np.float32)
                    minima_inds[:,0] += pp_cwt_min_scale_input.value
                    minima_inds[:,1] = minima_inds[:,1] * time_per_pixel + self.library[plate][well][compound].time[0]
                    maxima_inds = maxima_inds.astype(np.float32)
                    maxima_inds[:,0] += pp_cwt_min_scale_input.value
                    maxima_inds[:,1] = maxima_inds[:,1] * time_per_pixel + self.library[plate][well][compound].time[0]
                    
                    
            except Exception as e:
                self.status_text.value = "cwt_analysis_dmap: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
            return hv.Overlay([
                hv.Image(cwtmatr[::-1,:], kdims=['x', 'cwt_scale'], bounds=bounds).opts(cmap='viridis'),
                hv.Scatter({'x': minima_inds[:,1], 'cwt_scale': minima_inds[:,0], 'min_score': minima_scores}, kdims='x', vdims=['cwt_scale', 'min_score']).opts(framewise=True, color='min_score', cmap='kbc'),#, color='#BCFEAB'),
                hv.Scatter({'x': maxima_inds[:,1], 'cwt_scale': maxima_inds[:,0], 'max_score': maxima_scores}, kdims='x', vdims=['cwt_scale', 'max_score']).opts(framewise=True, color='max_score', cmap='kr')#, color='#0218DB')
            ])
        cwt_analysis_plot = hv.DynamicMap(cwt_analysis_dmap, streams=[Stream.define('Next')()]).opts(framewise=True)
        
        
        #Final view assembly
        pp_param_control_box = pn.WidgetBox(
            pp_sigma_input,
            pp_friction_input,
            pp_drop_baseline_checkbox,
            'Standard Curve (optional)',
            pn.Row(pp_stcurve_slope, pp_stcurve_intercept),
            pn.Row(
                pn.Column(
                    pn.pane.Markdown("<b>Auto</br>Integrate</b>"),
                    pp_integrate_selection_button,
                    pp_integrate_plate_button,
                    pp_integrate_library_button,
                ),
                pn.Column(
                    pn.pane.Markdown("<b>Drift Corr.</b></br> "),
                    pp_drift_correct_selection_button,
                    pp_drift_correct_plate_button,
                    pp_clear_drift_correct_selection_button,
                    pp_clear_drift_correct_plate_button,
                )
            )
        )
        pp_peak_features_box = pn.WidgetBox('Calculated Peak<br>Features', pp_peak_rt_display,
                                pp_peak_area_display, pp_peak_height_display, pp_peak_snr_display,
                                pp_peak_stcurve_area
                                )

        pp_advanced_options = pn.Card(pn.Column(
            pn.pane.Markdown('<b>Fine Region Control</b>'),
            pn.Row(pp_rt_input, pp_rt_tolerance, pp_left_bound, pp_right_bound),
            pn.pane.Markdown('<b>CWT Analysis</b>'),
            pn.Row(pp_cwt_min_scale_input, pp_cwt_max_scale_input, pp_cwt_neighborhood_input),
            pp_cwt_analysis_button,
            cwt_analysis_plot.opts(width=500, height=250)
        ), title='Advanced', sizing_mode='stretch_width', collapsed=True)

        peak_processing_view = pn.Column(
            pn.Row(
                self.pp_plate_selector, 
                self.pp_compound_selector,
                pp_download_csv_button,
            ), 
            pn.Row(
                pp_param_control_box, 
                pn.Column(
                    pn.pane.Markdown("<b>Double click on left and right of peak to select for integration (a little slow)</b>"),
                    selection_view.plot.opts(width=500, height=250),
                    pn.pane.Markdown("<b>Click to show well chromatogram.  Double click to clear</b>"),
                    plate_view.plot.opts(width=500, height=325),
                    pp_advanced_options
                ), 
                pp_peak_features_box
            )
        )
        
        #Event watchdogs and callbacks
        def selection_change():
            if (selection_view.selection_end != None):
                pp_integrate_plate_button.disabled = False
                pp_integrate_library_button.disabled = False
                pp_drift_correct_plate_button.disabled = False
                if len(plate_view.well_list) > 0:
                    pp_integrate_selection_button.disabled = False
                    if len(plate_view.well_list) > 1:
                        pp_drift_correct_selection_button.disabled = False
                    else:
                        pp_drift_correct_selection_button.disabled = True
                else:
                    pp_integrate_selection_button.disabled = True
            else:
                pp_integrate_selection_button.disabled = True
                pp_integrate_plate_button.disabled = True
                pp_integrate_library_button.disabled = True
                pp_drift_correct_selection_button.disabled = True
                pp_drift_correct_plate_button.disabled = True

            if len(plate_view.well_list) > 0:
                pp_clear_drift_correct_selection_button.disabled = False
            else:
                pp_clear_drift_correct_selection_button.disabled = True
                

            def out_format(v1, v2=None):
                if v2 != None:
                    if (v1 > 1.0E+3) or (v2 > 1.0E+3):
                        return f"{v1:.2e}±{v2:.2e}"
                    else:
                        return f"{v1:.2f}±{v2:.2e}"
                else:
                    if v1 > 1.0E+3:
                        return f"{v1:.2e}"
                    else:
                        return f"{v1:.2f}"
                    
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            disp_well_list = [well for well in plate_view.well_list if self.library[plate][well][compound].peak_area != None]

            if len(disp_well_list) == 0:
                pp_peak_rt_display.value = ""
                pp_peak_area_display.value = ""
                pp_peak_height_display.value = ""
                pp_peak_snr_display.value = ""
                pp_peak_stcurve_area.value = ""
            else:
                if len(disp_well_list) == 1:
                    well = disp_well_list[0]
                    pp_peak_rt_display.value = out_format(self.library[plate][well][compound].peak_rt)
                    pp_peak_area_display.value = out_format(self.library[plate][well][compound].peak_area)
                    pp_peak_height_display.value = out_format(self.library[plate][well][compound].peak_height)
                    pp_peak_snr_display.value = out_format(self.library[plate][well][compound].peak_snr)
                    if self.library[plate][well][compound].peak_stcurve_area != None:
                        pp_peak_stcurve_area.value = out_format(self.library[plate][well][compound].peak_stcurve_area)
                    else:
                        pp_peak_stcurve_area.value = "N/A"
                else:
                    n_wells = len(disp_well_list)
                    rts = np.zeros(n_wells)
                    areas = np.zeros(n_wells)
                    heights = np.zeros(n_wells)
                    snrs = np.zeros(n_wells)
                    stcurve_areas = np.zeros(n_wells)
                    all_stcurve = True
                    for i, well in enumerate(disp_well_list):
                        rts[i] = self.library[plate][well][compound].peak_rt
                        areas[i] = self.library[plate][well][compound].peak_area
                        heights[i] = self.library[plate][well][compound].peak_height
                        snrs[i] = self.library[plate][well][compound].peak_snr
                        if self.library[plate][well][compound].peak_stcurve_area != None:
                            stcurve_areas[i] = self.library[plate][well][compound].peak_stcurve_area
                        else:
                            all_stcurve = False
                    pp_peak_rt_display.value = out_format(np.average(rts), np.std(rts))
                    pp_peak_area_display.value = out_format(np.average(areas), np.std(areas))
                    pp_peak_height_display.value = out_format(np.average(heights), np.std(heights))
                    pp_peak_snr_display.value = out_format(np.average(snrs), np.std(snrs))
                    if all_stcurve:
                        pp_peak_stcurve_area.value = out_format(np.average(stcurve_areas), np.std(stcurve_areas))
                    else:
                        pp_peak_stcurve_area.value = "N/A"

        def pp_plate_selector_watchdog(event):
            try:
                if (event.new != None) and (event.new != ""):
                    compounds = list(self.library[event.new].compounds)
                    if self.pp_compound_selector.value in compounds:
                        new_sele = self.pp_compound_selector.value
                    else:
                        new_sele = compounds[0]
                    self.pp_compound_selector.param.update({'options': compounds, 'value': new_sele})
            except Exception as e:
                self.status_text.value = "pp_plate_selector_watchdog: " + str(e)
                self.debug_text.value += f"Plate: >{event.new}\t>{type(event.new)}"
                self.debug_text.value += traceback.format_exc() + "\n\n"
        self.pp_plate_selector.param.watch(pp_plate_selector_watchdog, ['value'], onlychanged=False)
        
        def pp_compound_selector_watchdog(event):
            try:
                plate = self.pp_plate_selector.value
                if (event.new != None) and (plate != None):
                    #Update our well selections if we have previous ones
                    if len(plate_view.well_list) > 0:
                        #Only retain wells which have the newly selected compound
                        for i in range(len(plate_view.well_list)-1, -1, -1):
                            if plate_view.well_list[i] not in self.library[plate]:
                                del plate_view.well_list[i]
                            elif event.new not in self.library[plate][plate_view.well_list[i]]:
                                del plate_view.well_list[i]
                        plate_view.highlight_plot.event()
                    plate_view.plate_plot.event()
                    selection_view.overlay_plot.event()
                    selection_view.integration_statistics_plot.event()
            except Exception as e:
                self.debug_text.value += f"Well: {event.new}\t{type(event.new)}"
                self.status_text.value = "pp_compound_selector_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        self.pp_compound_selector.param.watch(pp_compound_selector_watchdog, ['value'], onlychanged=False)

        def pp_integrate_selection_button_callback(event):
            try:
                self.status_text.value = "Integrating selected wells..."
                plate = self.pp_plate_selector.value
                compound = self.pp_compound_selector.value
                for i, well in enumerate(plate_view.well_list, 1):
                    if compound in self.library[plate][well]:
                        stcurve_slope = None
                        stcurve_intercept = None
                        if (pp_stcurve_slope.value != 0) and (pp_stcurve_slope.value != None) and (pp_stcurve_intercept.value != None):
                            stcurve_slope = pp_stcurve_slope.value
                            stcurve_intercept = pp_stcurve_intercept.value
                        self.library[plate][well][compound].set_processing_parameters(
                            pp_rt_input.value,
                            pp_rt_tolerance.value,
                            pp_left_bound.value,
                            pp_right_bound.value,
                            pp_sigma_input.value,
                            pp_cwt_min_scale_input.value,
                            pp_cwt_max_scale_input.value,
                            pp_cwt_neighborhood_input.value,
                            pp_friction_input.value,
                            pp_drop_baseline_checkbox.value,
                            stcurve_slope,
                            stcurve_intercept
                        )
                        self.library[plate][well][compound].process_peak()
                    self.progress_bar.value = int(np.round((100 * i) / len(self.library[plate])))
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                plate_view.plate_plot.event()
                self.status_text.value = "Done integrating well!"
            except Exception as e:
                self.status_text.value = "pp_integrate_plate_button_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        pp_integrate_selection_button.on_click(pp_integrate_selection_button_callback)

        def pp_integrate_plate_button_callback(event):
            try:
                self.status_text.value = "Integrating plate..."
                plate = self.pp_plate_selector.value
                compound = self.pp_compound_selector.value
                for i, well in enumerate(self.library[plate], 1):
                    if compound in self.library[plate][well]:
                        self.library[plate][well][compound].set_processing_parameters(
                            pp_rt_input.value,
                            pp_rt_tolerance.value,
                            pp_left_bound.value,
                            pp_right_bound.value,
                            pp_sigma_input.value,
                            pp_cwt_min_scale_input.value,
                            pp_cwt_max_scale_input.value,
                            pp_cwt_neighborhood_input.value,
                            pp_friction_input.value,
                            pp_drop_baseline_checkbox.value
                        )
                        self.library[plate][well][compound].process_peak()
                    self.progress_bar.value = int(np.round((100 * i) / len(self.library[plate])))
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                plate_view.plate_plot.event()
                self.status_text.value = "Done integrating plate!"
            except Exception as e:
                self.status_text.value = "pp_integrate_plate_button_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        pp_integrate_plate_button.on_click(pp_integrate_plate_button_callback)

        def pp_integrate_library_button_callback(event):
            try:
                self.status_text.value = "Integrating library..."
                compound = self.pp_compound_selector.value
                for i, plate in enumerate(self.library):
                    for j, well in enumerate(self.library[plate], 1):
                        if compound in self.library[plate][well]:
                            self.library[plate][well][compound].set_processing_parameters(
                                pp_rt_input.value,
                                pp_rt_tolerance.value,
                                pp_left_bound.value,
                                pp_right_bound.value,
                                pp_sigma_input.value,
                                pp_cwt_min_scale_input.value,
                                pp_cwt_max_scale_input.value,
                                pp_cwt_neighborhood_input.value,
                                pp_friction_input.value,
                                pp_drop_baseline_checkbox.value
                            )
                            self.library[plate][well][compound].process_peak()
                        self.progress_bar.value = int(np.round(100 * ((i/len(self.library)) + ((1/len(self.library)) * (j/len(self.library[plate]))))))
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                plate_view.plate_plot.event()
                self.status_text.value = "Done integrating library!"
            except Exception as e:
                self.status_text.value = "pp_integrate_library_button_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        pp_integrate_library_button.on_click(pp_integrate_library_button_callback)

        def pp_drift_correct_selection_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            sigma = pp_sigma_input.value
            n_wells = len(plate_view.well_list)
            if n_wells < 2:
                self.status_text.value = "At least 2 wells must be selected for drift correction"
            else:
                self.status_text.value = "Determining average maxima position..."
                self.progress_bar.value = 0
                maxima_times = []
                for i, well in enumerate(plate_view.well_list):
                    if compound in self.library[plate][well]:
                        time_start_ind = np.argmin(np.abs(selection_view.selection_start - self.library[plate][well][compound].time))
                        time_end_ind = np.argmin(np.abs(selection_view.selection_end - self.library[plate][well][compound].time))
                        maxima_times.append(self.library[plate][well][compound].time[
                                time_start_ind + np.argmax(gaussian_filter1d(self.library[plate][well][compound].intensity, sigma)[time_start_ind:time_end_ind])
                            ])
                        self.progress_bar.value = int(np.round((100 * (i+1)) / (n_wells*2)))
                self.status_text.value = "Applying drift correction..."
                average_time = np.average(maxima_times)
                n_wells = len(maxima_times)
                for i, well in enumerate(plate_view.well_list):
                    if compound in self.library[plate][well]:
                        self.library[plate][well][compound].drift_offset = (average_time - maxima_times[i])
                        self.progress_bar.value = int(np.round((100 * (i+1+n_wells)) / (n_wells*2)))
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                self.status_text.value = "Done applying drift correction to selection!"
        pp_drift_correct_selection_button.on_click(pp_drift_correct_selection_button_callback)

        def pp_drift_correct_plate_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            sigma = pp_sigma_input.value
            n_wells = len(self.library[plate])
            if n_wells < 2:
                self.status_text.value = "At least 2 wells must be present for drift correction"
            else:
                self.status_text.value = "Determining average maxima position..."
                self.progress_bar.value = 0
                maxima_times = []
                for i, well in enumerate(self.library[plate]):
                    if compound in self.library[plate][well]:
                        time_start_ind = np.argmin(np.abs(selection_view.selection_start - self.library[plate][well][compound].time))
                        time_end_ind = np.argmin(np.abs(selection_view.selection_end - self.library[plate][well][compound].time))
                        maxima_times.append(self.library[plate][well][compound].time[
                                time_start_ind + np.argmax(gaussian_filter1d(self.library[plate][well][compound].intensity, sigma)[time_start_ind:time_end_ind])
                            ])
                    self.progress_bar.value = int(np.round((100 * (i+1)) / (n_wells*2)))
                self.status_text.value = "Applying drift correction..."
                average_time = np.average(maxima_times)
                n_wells = len(maxima_times)
                for i, well in enumerate(self.library[plate]):
                    if compound in self.library[plate][well]:
                        self.library[plate][well][compound].drift_offset = (average_time - maxima_times[i])
                        self.progress_bar.value = int(np.round((100 * (i+1+n_wells)) / (n_wells*2)))
                selection_view.overlay_plot.event()
                selection_view.integration_statistics_plot.event()
                self.status_text.value = "Done applying drift correction to selection!"
        pp_drift_correct_plate_button.on_click(pp_drift_correct_plate_button_callback)

        def pp_clear_drift_correct_selection_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            for well in plate_view.well_list:
                self.library[plate][well][compound].drift_offset = 0
            selection_view.overlay_plot.event()
            selection_view.integration_statistics_plot.event()
        pp_clear_drift_correct_selection_button.on_click(pp_clear_drift_correct_selection_button_callback)

        def pp_clear_drift_correct_plate_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            for well in self.library[plate]:
                self.library[plate][well][compound].drift_offset = 0
            selection_view.overlay_plot.event()
            selection_view.integration_statistics_plot.event()
        pp_clear_drift_correct_plate_button.on_click(pp_clear_drift_correct_plate_button_callback)

        def pp_cwt_analysis_button_callback(event):
            cwt_analysis_plot.event()
        pp_cwt_analysis_button.on_click(pp_cwt_analysis_button_callback)

        return peak_processing_view
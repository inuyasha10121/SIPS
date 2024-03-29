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
from holoviews.streams import Stream, DoubleTap, SingleTap, BoundsX

from bokeh import palettes

from .PlateClass import Library
from .global_utils import get_pn_id_token


sidebar_text = """### MS-FIT
This pane is responsible for processing and integrating chromatography data.  

* The upper plot shows an overlay of all the chromatograms of the specified compound in the plate, or any chromatograms from selected wells
  * Use the "Box Select" tool (right side toolbar) to specify an integration region for the compound, which will be shown in blue
  * If integration data is available, the integration regions, baselines, and peak heights will also be displayed
* The middle plot shows a plate heatmap of the integrated peak areas.
  * If a well is not present, it will be gray.  
  * If a well has not been integrated yet, it will be white.
  * Select subsets of wells to view in the upper plot by clicking them.  Clicking again will de-select the well.  If a well is selected, it will be bordered in white.
* The advanced tab allows for showing the Continuous Wavelet Transform (CWT) results, as well as fine tuning of parameters (see documentation)
* On the left:
  * "Selected" applies the specified processing to any wells you have selected, and only becomes available when wells are selected
  * "Plate" applies the specified processing to all available wells in the plate
  * "Library" applies the specified processing to all plates in the library

The workflow for processing data is as follows:

* Load the desired plate and compound using the dropdown menus
* Change the "Smoothing Factor" to make smooth gaussian peaks
* If available, slope/intercept information from a standard curve can also be provided
* Select an integration region in the upper plot using the "Box Select" tool
* If the peaks are poorly grouped, you can use "Drift Corr." to align the peaks and re-specify the integration region
* Run an initial integration, then select a few wells to see how well the integration performed
* If the peak edges are very far from the peak, you can increase "Friction Threshold" to reduce by how much the initial bounds are moved
* If your peak is co-eluting, "Drop baseline" can be used to avoid steep baselines
* If proper integration is still failing, you can open the 'Advanced' menu to fine tune parameters
  * "Retention Time" specifies the center of the peak search area.  This should be close to the center of your peaks.
  * "Retention Time Tolerance" specifies the maximumm distance away from the retention time that a peak will likely to be chosen.
  * "Left Bound" specifies the initial left bound of the peak, which is then relaxed and optimized
  * "Right Bound" specifies the initial right bound of the peak, which is then relaxed and optimized
  * "CWT Min Scale" specifies the minimum scale used in the CWT analysis.  The smaller the value, the more small features will be considered peaks
  * "CWT Max Scale" specifies the maximum scale used in the CWT analysis.  The larger the value, the more large features will be considered peaks
  * "CWT Neighborhood" specifies how many neighboring pixles are checked when searching for local minima/maxima.  Increasing this can reduce the number of false peaks/edges
  * "CWT Analysis" shows the CWT analysis data for a single selected well.  Detected peaks are indicated by yellow regions, while detected valleys (peak edges) are indicated by dark blue regions.
    * Ideally, you should see a strong yellow region flanked by strong dark blue regions.  If you don't see this, try increasing the "Smoothing Factor" to make the peaks more gaussian in shape.
"""

class module_class:
    def __init__(self, tab_id, status_text: pn.widgets.TextInput, progress_bar: pn.widgets.Progress, debug_text: pn.widgets.TextInput):
        self.tab_id = tab_id
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
                        library: Library = pn.state.cache['id_tokens'][get_pn_id_token()]['library']
                        sidebar_info.object = sidebar_text
                        plates = list(library)
                        if len(plates) > 0:
                            self.pp_plate_selector.options = plates
                        else:
                            self.pp_plate_selector.options = []
            except Exception as e:
                self.status_text.value = "tab_selection_callback" + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        tab_set.param.watch(tab_selection_callback, ['active'], onlychanged=False)

    def pane_definition(self):
        library: Library = pn.state.cache['id_tokens'][get_pn_id_token()]['library']
        
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
        
        pp_peak_source_display = pn.widgets.TextInput(name='Source', width=150, disabled=True)
        pp_peak_rt_display = pn.widgets.TextInput(name='Retention Time', width=150, disabled=True)
        pp_peak_area_display = pn.widgets.TextInput(name='Area', width=150, disabled=True)
        pp_peak_height_display = pn.widgets.TextInput(name='Height', width=150, disabled=True)
        pp_peak_snr_display = pn.widgets.TextInput(name='SNR', width=150, disabled=True)
        pp_peak_stcurve_area = pn.widgets.TextInput(name='St. Curve', placeholder='N/A', width=150, disabled=True)

        pp_cwt_analysis_button = pn.widgets.Button(name='CWT Analysis', button_type='primary')

        def download_data_csv_callback():
            try:
                #First, get all our compounds
                compounds = set()
                for plate in library:
                    for well in library[plate]:
                        compounds.update(set(library[plate][well]))
                columns = ['Plate', 'Well', 'Sample'] + list(compounds)
                n_columns = len(columns)
                #Harvest our data
                well_order = [f"{chr(65+i)}{str(j).zfill(2)}" for j in range(1,13) for i in range(8)]
                data = []
                for plate in library:
                    for well in well_order:
                        if well in library[plate]:
                            data.append(['' for _ in range(n_columns)])
                            data[-1][0] = plate
                            data[-1][1] = well
                            
                            for compound in library[plate][well]:
                                if library[plate][well][compound].sample_name != None:
                                    data[-1][2] = library[plate][well][compound].sample_name
                                data[-1][columns.index(compound)] = library[plate][well][compound].peak_area
                #Send a stream to the file download widget
                sio = StringIO()
                pd.DataFrame(data, columns=columns).to_csv(sio, index=False)
                sio.seek(0)
                return sio
            except Exception as e:
                self.status_text.value = "download_data_csv_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
                
        
        pp_download_csv_button = pn.widgets.FileDownload(
            name='Download',
            callback=download_data_csv_callback, filename='library_integration_data.csv',
            width = 125, button_type='primary', label='Download .csv'
        )

        pp_download_filename = pn.widgets.TextInput(name='Filename:', placeholder='library_integration_data.csv', width=200)
        
        def download_data_plate_callback():
            try:
                #First, get all our compounds
                compounds = set()
                for plate in library:
                    for well in library[plate]:
                        compounds.update(set(library[plate][well]))
                columns = ['Plate', 'Well'] + list(compounds)
                n_columns = len(columns)
                #Harvest our data
                data = []
                for plate in library:
                    for well in library[plate]:
                        data.append(['' for _ in range(n_columns)])
                        data[-1][0] = plate
                        data[-1][1] = well
                        for compound in library[plate][well]:
                            data[-1][columns.index(compound)] = library[plate][well][compound].peak_area
                #Send a stream to the file download widget
                sio = StringIO()
                pd.DataFrame(data, columns=columns).to_csv(sio, index=False)
                sio.seek(0)
                return sio
            except Exception as e:
                self.status_text.value = "download_data_plate_callback: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
                
        
        pp_download_plate_button = pn.widgets.FileDownload(
            name='Download',
            callback=download_data_plate_callback, filename='plate.png',
            width = 125, button_type='primary', label='Download .png'
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
                print(well)
                if well in self.well_list:
                    del self.well_list[self.well_list.index(well)]
                    selection_view.update_overlay_plot()
                    selection_view.integration_statistics_plot.event()
                    self.highlight_plot.event()
                    selection_change()
                else:
                    if well in self.outer_instance.library[plate]:
                        self.well_list.append(well)
                        selection_view.update_overlay_plot()
                        selection_view.integration_statistics_plot.event()
                        self.highlight_plot.event()
                        selection_change()

            def double_tap_clear(self, x, y):
                self.well_list = []
                selection_view.update_overlay_plot()
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
            def __init__(self, outer_instance, **params):
                super().__init__(**params)
                self.outer_instance = outer_instance #Grab outer so we can access the Library
                #Setup overlay plot bits
                self.update_overlay_plot_stream = Stream.define('flag', flag=False)()
                self.selection_stream = BoundsX(boundsx=(0,0))
                self.selection_stream.param.watch(self.range_selection_input, ['boundsx'], onlychanged=False)
                self.overlay_plot = hv.DynamicMap(self.overlay_plot_dmap, streams=[self.selection_stream, self.update_overlay_plot_stream]).opts(framewise=True, tools=['hover', 'xbox_select', 'box_zoom'])
                self.integration_statistics_plot = hv.DynamicMap(self.integration_statistics_dmap, streams=[Stream.define('Next')()]).opts(framewise=True)
                self.integration_region_plot = hv.DynamicMap(self.selection_plot_dmap, streams=[self.selection_stream]).opts(framewise=True)
                self.plot = (self.integration_region_plot * self.overlay_plot * self.integration_statistics_plot).opts(show_legend=False, framewise=True).opts(
                    opts.Curve(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity', framewise=True),
                    opts.Area(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity', framewise=True),
                    opts.VSpan(default_tools=['pan', 'wheel_zoom', 'reset'], xlabel='Time', ylabel='Intensity', framewise=True)
                )

            def update_overlay_plot(self):
                self.update_overlay_plot_stream.event(flag=not self.update_overlay_plot_stream.flag)
            
            def overlay_plot_dmap(self, **kwargs):
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
                                #Get our time and smoothed chromatogram
                                x = self.outer_instance.library[plate][well][compound].time + self.outer_instance.library[plate][well][compound].drift_offset
                                y = gaussian_filter1d(self.outer_instance.library[plate][well][compound].intensity, pp_sigma_input.value)
                                #Add the chromatogram curve to our dictionary
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
            
            def selection_plot_dmap(self, boundsx):
                return hv.VSpan(boundsx[0], boundsx[1])

            def range_selection_input(self, event):
                try:
                    if (event.new[0] != None) and (event.new[1] != None):
                        pp_left_bound.value = event.new[0]
                        pp_right_bound.value = event.new[1]
                        pp_rt_input.value = (event.new[0] + event.new[1]) / 2
                        pp_rt_tolerance.value = (event.new[1] - event.new[0]) / 2
                        selection_change()
                except Exception as e:
                    self.outer_instance.status_text.value = "range_selection_input: " + str(e)
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
                else:
                    plate = self.pp_plate_selector.value
                    well = plate_view.well_list[0]
                    compound = self.pp_compound_selector.value
                    self.status_text.value = "Performing CWT analysis..."
                    #Set relevant parameters for well
                    library[plate][well][compound].rt = pp_rt_input.value
                    library[plate][well][compound].rt_tolerance = pp_rt_tolerance.value
                    library[plate][well][compound].sigma = pp_sigma_input.value
                    library[plate][well][compound].cwt_min_scale = pp_cwt_min_scale_input.value
                    library[plate][well][compound].cwt_max_scale = pp_cwt_max_scale_input.value
                    library[plate][well][compound].cwt_neighborhood = pp_cwt_neighborhood_input.value
                    library[plate][well][compound].peak_bound_inds = [
                        np.argmin(np.abs(pp_left_bound.value - library[plate][well][compound].time)), 
                        np.argmin(np.abs(pp_right_bound.value - library[plate][well][compound].time))
                    ]
                    #Perform CWT peak finding workflow
                    smoothed_chromatogram = library[plate][well][compound].gaussian_smoothing()
                    second_deriv = library[plate][well][compound].second_deriv(smoothed_chromatogram)
                    cwtmatr = library[plate][well][compound].cwt_generation(second_deriv)
                    self.status_text.value = "Finding minima/maxima in selection range..."
                    minima_inds, maxima_inds = library[plate][well][compound].cwt_analysis(cwtmatr)
                    #Restrict minima/maxima to defined integration region
                    mask = (maxima_inds[:,1] >= library[plate][well][compound].peak_bound_inds[0]) & (maxima_inds[:,1] <= library[plate][well][compound].peak_bound_inds[1])
                    maxima_inds = maxima_inds[mask,:]
                    span = library[plate][well][compound].peak_bound_inds[1] - library[plate][well][compound].peak_bound_inds[0]
                    mask = (minima_inds[:,1] >= (library[plate][well][compound].peak_bound_inds[0] - span)) & (minima_inds[:,1] <= (library[plate][well][compound].peak_bound_inds[1] + span))
                    minima_inds = minima_inds[mask,:]
                    #Figure out bounds with appropriate padding
                    time_per_pixel = (library[plate][well][compound].time[-1] - library[plate][well][compound].time[0]) / cwtmatr.shape[1]
                    bounds = [
                        library[plate][well][compound].time[0] - (time_per_pixel/2),
                        pp_cwt_min_scale_input.value - 0.5,
                        library[plate][well][compound].time[-1] + (time_per_pixel/2),
                        pp_cwt_max_scale_input.value + 0.5
                    ]
                    #Map minima and maxima indicies to time values
                    minima_inds = minima_inds.astype(np.float32)
                    minima_inds[:,0] += pp_cwt_min_scale_input.value
                    minima_inds[:,1] = minima_inds[:,1] * time_per_pixel + library[plate][well][compound].time[0]
                    maxima_inds = maxima_inds.astype(np.float32)
                    maxima_inds[:,0] += pp_cwt_min_scale_input.value
                    maxima_inds[:,1] = maxima_inds[:,1] * time_per_pixel + library[plate][well][compound].time[0]
                    
                    
            except Exception as e:
                self.status_text.value = "cwt_analysis_dmap: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
            return hv.Overlay([
                hv.Image(cwtmatr[::-1,:], kdims=['x', 'cwt_scale'], bounds=bounds).opts(cmap='viridis'),
                hv.Scatter({'x': minima_inds[:,1], 'cwt_scale': minima_inds[:,0]}, kdims='x', vdims='cwt_scale').opts(framewise=True, color='c'),
                hv.Scatter({'x': maxima_inds[:,1], 'cwt_scale': maxima_inds[:,0]}, kdims='x', vdims='cwt_scale').opts(framewise=True, color='r')
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
        pp_peak_features_box = pn.WidgetBox(pp_peak_source_display, 'Calculated Peak<br>Features', pp_peak_rt_display,
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
                pp_download_filename,
                pp_download_csv_button,
            ), 
            pn.Row(
                pp_param_control_box, 
                pn.Column(
                    pn.pane.Markdown("<b>Use the \"Box Select\" tool on the right to click-drag an integration region</b>"),
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
            if (selection_view.selection_stream.boundsx[0] != None):
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
            disp_well_list = [well for well in plate_view.well_list if library[plate][well][compound].peak_area != None]

            if len(disp_well_list) == 0:
                pp_peak_source_display.value = ""
                pp_peak_rt_display.value = ""
                pp_peak_area_display.value = ""
                pp_peak_height_display.value = ""
                pp_peak_snr_display.value = ""
                pp_peak_stcurve_area.value = ""
            else:
                if len(disp_well_list) == 1:
                    well = disp_well_list[0]
                    pp_peak_source_display.value = library[plate][well][compound].source
                    pp_peak_rt_display.value = out_format(library[plate][well][compound].peak_rt)
                    pp_peak_area_display.value = out_format(library[plate][well][compound].peak_area)
                    pp_peak_height_display.value = out_format(library[plate][well][compound].peak_height)
                    pp_peak_snr_display.value = out_format(library[plate][well][compound].peak_snr)
                    if library[plate][well][compound].peak_stcurve_area != None:
                        pp_peak_stcurve_area.value = out_format(library[plate][well][compound].peak_stcurve_area)
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
                    pp_peak_source_display.value = ", ".join([library[plate][well][compound].source for well in disp_well_list])
                    for i, well in enumerate(disp_well_list):
                        rts[i] = library[plate][well][compound].peak_rt
                        areas[i] = library[plate][well][compound].peak_area
                        heights[i] = library[plate][well][compound].peak_height
                        snrs[i] = library[plate][well][compound].peak_snr
                        if library[plate][well][compound].peak_stcurve_area != None:
                            stcurve_areas[i] = library[plate][well][compound].peak_stcurve_area
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

        def pp_download_filename_watchdog(event):
            if (event.new == "") or (event.new == None):
                pp_download_csv_button.filename = 'library_integration_data.csv'
            elif not event.new.endswith('.csv'):
                pp_download_csv_button.filename = f"{event.new}.csv"
            else:
                pp_download_csv_button.filename = event.new
        pp_download_filename.param.watch(pp_download_filename_watchdog, ['value'], onlychanged=False)

        def pp_plate_selector_watchdog(event):
            try:
                if (event.new != None) and (event.new != ""):
                    compounds = list(library[event.new].compounds)
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
                            if plate_view.well_list[i] not in library[plate]:
                                del plate_view.well_list[i]
                            elif event.new not in library[plate][plate_view.well_list[i]]:
                                del plate_view.well_list[i]
                        plate_view.highlight_plot.event()
                    plate_view.plate_plot.event()
                    selection_view.update_overlay_plot()
                    selection_view.integration_statistics_plot.event()
            except Exception as e:
                self.debug_text.value += f"Well: {event.new}\t{type(event.new)}"
                self.status_text.value = "pp_compound_selector_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        self.pp_compound_selector.param.watch(pp_compound_selector_watchdog, ['value'], onlychanged=False)

        def pp_sigma_input_watchdog(event):
            try:
                selection_view.update_overlay_plot()
            except Exception as e:
                self.status_text.value = "pp_sigma_input_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        pp_sigma_input.param.watch(pp_sigma_input_watchdog, ['value'], onlychanged=False)

        def pp_integrate_selection_button_callback(event):
            try:
                self.status_text.value = "Integrating selected wells..."
                plate = self.pp_plate_selector.value
                compound = self.pp_compound_selector.value
                for i, well in enumerate(plate_view.well_list, 1):
                    if compound in library[plate][well]:
                        stcurve_slope = None
                        stcurve_intercept = None
                        if (pp_stcurve_slope.value != 0) and (pp_stcurve_slope.value != None) and (pp_stcurve_intercept.value != None):
                            stcurve_slope = pp_stcurve_slope.value
                            stcurve_intercept = pp_stcurve_intercept.value
                        library[plate][well][compound].set_processing_parameters(
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
                        library[plate][well][compound].process_peak()
                    self.progress_bar.value = int(np.round((100 * i) / len(library[plate])))
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
                for i, well in enumerate(library[plate], 1):
                    if compound in library[plate][well]:
                        library[plate][well][compound].set_processing_parameters(
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
                        library[plate][well][compound].process_peak()
                    self.progress_bar.value = int(np.round((100 * i) / len(library[plate])))
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
                for i, plate in enumerate(library):
                    for j, well in enumerate(library[plate], 1):
                        if compound in library[plate][well]:
                            library[plate][well][compound].set_processing_parameters(
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
                            library[plate][well][compound].process_peak()
                        self.progress_bar.value = int(np.round(100 * ((i/len(library)) + ((1/len(library)) * (j/len(library[plate]))))))
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
                    if compound in library[plate][well]:
                        time_start_ind = np.argmin(np.abs(pp_left_bound.value - library[plate][well][compound].time))
                        time_end_ind = np.argmin(np.abs(pp_right_bound.value - library[plate][well][compound].time))
                        maxima_times.append(library[plate][well][compound].time[
                                time_start_ind + np.argmax(gaussian_filter1d(library[plate][well][compound].intensity, sigma)[time_start_ind:time_end_ind])
                            ])
                        self.progress_bar.value = int(np.round((100 * (i+1)) / (n_wells*2)))
                self.status_text.value = "Applying drift correction..."
                average_time = np.average(maxima_times)
                n_wells = len(maxima_times)
                for i, well in enumerate(plate_view.well_list):
                    if compound in library[plate][well]:
                        library[plate][well][compound].drift_offset = (average_time - maxima_times[i])
                        self.progress_bar.value = int(np.round((100 * (i+1+n_wells)) / (n_wells*2)))
                selection_view.update_overlay_plot()
                selection_view.integration_statistics_plot.event()
                self.status_text.value = "Done applying drift correction to selection!"
        pp_drift_correct_selection_button.on_click(pp_drift_correct_selection_button_callback)

        def pp_drift_correct_plate_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            sigma = pp_sigma_input.value
            n_wells = len(library[plate])
            if n_wells < 2:
                self.status_text.value = "At least 2 wells must be present for drift correction"
            else:
                self.status_text.value = "Determining average maxima position..."
                self.progress_bar.value = 0
                maxima_times = []
                for i, well in enumerate(library[plate]):
                    if compound in library[plate][well]:
                        time_start_ind = np.argmin(np.abs(pp_left_bound.value - library[plate][well][compound].time))
                        time_end_ind = np.argmin(np.abs(pp_right_bound.value - library[plate][well][compound].time))
                        maxima_times.append(library[plate][well][compound].time[
                                time_start_ind + np.argmax(gaussian_filter1d(library[plate][well][compound].intensity, sigma)[time_start_ind:time_end_ind])
                            ])
                    self.progress_bar.value = int(np.round((100 * (i+1)) / (n_wells*2)))
                self.status_text.value = "Applying drift correction..."
                average_time = np.average(maxima_times)
                n_wells = len(maxima_times)
                for i, well in enumerate(library[plate]):
                    if compound in library[plate][well]:
                        library[plate][well][compound].drift_offset = (average_time - maxima_times[i])
                        self.progress_bar.value = int(np.round((100 * (i+1+n_wells)) / (n_wells*2)))
                selection_view.update_overlay_plot()
                selection_view.integration_statistics_plot.event()
                self.status_text.value = "Done applying drift correction to selection!"
        pp_drift_correct_plate_button.on_click(pp_drift_correct_plate_button_callback)

        def pp_clear_drift_correct_selection_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            for well in plate_view.well_list:
                library[plate][well][compound].drift_offset = 0
            selection_view.update_overlay_plot()
            selection_view.integration_statistics_plot.event()
        pp_clear_drift_correct_selection_button.on_click(pp_clear_drift_correct_selection_button_callback)

        def pp_clear_drift_correct_plate_button_callback(event):
            plate = self.pp_plate_selector.value
            compound = self.pp_compound_selector.value
            for well in library[plate]:
                library[plate][well][compound].drift_offset = 0
            selection_view.update_overlay_plot()
            selection_view.integration_statistics_plot.event()
        pp_clear_drift_correct_plate_button.on_click(pp_clear_drift_correct_plate_button_callback)

        def pp_cwt_analysis_button_callback(event):
            cwt_analysis_plot.event()
        pp_cwt_analysis_button.on_click(pp_cwt_analysis_button_callback)

        return peak_processing_view
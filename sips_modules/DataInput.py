import numpy as np

import panel as pn

import traceback

from custom_widgets.fileprogressinput import FileProgressInput
from custom_widgets.dataselectiontable import DataSelectionTable
from .PlateClass import *
from .global_utils import get_pn_id_token

sidebar_text = """### Data Input
SIPS takes the following data as inputs and file formats:

* Chromatography data (2D/3D, MS/PDA): Empower .arw raw data files containing well ID and detection type in the header
* Sequencing data is pending when AReS is re-implemented


To upload data, first add a new plate using the upper menu.  


If a plate needs to be deleted, simply select the plate from the dropdown and click the delete button.


As you input data, panels will pop up if additional information is required with guidance on how to input this data.

* For chromatography data:
  * Add compound names to the "Compound" column
  * Pick a data source from the "Source" dropdowns that the compound should come from
  * If the source is a 3D data channel, specify the wavelength or m/z value to extract from the 3D data


Please wait patiently for data to load (watch the loading indicators, including the upper right wheel, and status bar), some data takes quite a while to process and transfer to the server.
"""

class module_class:
    def __init__(self, tab_id, status_text, progress_bar, debug_text):
        self.tab_id = tab_id
        self.status_text = status_text
        self.progress_bar = progress_bar
        self.debug_text = debug_text
        
        self.fi_plate_selector = pn.widgets.Select(name='Plate selection:', options=["New Plate"], width=200)
        
    def bind_tab(self, tab_set, sidebar_info):
        tab_set.append(("Input", self.pane_definition()))
        def tab_selection_callback(event):
            try:
                if event.name == "active":
                    if event.new == self.tab_id: #Info
                        library: Library = pn.state.cache['id_tokens'][get_pn_id_token()]['library']
                        sidebar_info.object = sidebar_text
                        self.fi_plate_selector.options = ['New Plate'] + list(library.plates)
                        self.fi_plate_selector.value = 'New Plate'
            except Exception as e:
                self.status_text.value = "tab_selection_callback" + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        tab_set.param.watch(tab_selection_callback, ['active'])
    

    def pane_definition(self):
        library: Library = pn.state.cache['id_tokens'][get_pn_id_token()]['library']
        try:
            #Input declarations and section assembly
            fi_multi_upload = FileProgressInput(name='bk_fi_multi_upload', width=300, height=450, multiple=True)

            fi_plate_name = pn.widgets.TextInput(name='New plate name:', width=200)
            fi_add_plate_button = pn.widgets.Button(name='Add Plate', button_type='primary', width=200)
            fi_delete_plate_button = pn.widgets.Button(name='Delete Plate', button_type='danger', width=200, visible=False)
            fi_plate_module = pn.Column(
                "<h3>Plate Setup</h3>",
                pn.Row(
                    self.fi_plate_selector,
                    fi_plate_name,
                    fi_add_plate_button,
                    fi_delete_plate_button
                )
            )
            fi_target_table = DataSelectionTable(name='bk_fi_target_table')
            fi_parent_wells = pn.widgets.TextInput(name="Parent Wells:", placeholder="Seperated by spaces (ie, \"A06 B06...\")", width=300, height=50)
            fi_control_wells = pn.widgets.TextInput(name="Control Wells:", placeholder="Seperated by spaces (ie, \"A06 B06...\")", width=300, height=50)
            fi_compound_input_module = pn.Column(
                pn.pane.HTML(
                    """<h3>Chromatography Data</h3>
                    <b>Use \'Compound\' to give a unique name to each compound to extract</b></br>
                    <b>Use \'Target\' to specify the wavelength or m/z (Not required for 2D directories)</b>
                    """,
                    width=300,
                    height=120
                ),
                fi_parent_wells,
                fi_control_wells,
                fi_target_table,
                visible=False
            )

            fi_alignment_examples = pn.pane.Str(name="Example Entries:", width=300, height=125)
            fi_alignment_well_row_index = pn.widgets.IntInput(name="Row index (A,B,C...):", width=300, height=50)
            fi_alignment_well_column_index = pn.widgets.IntInput(name="Column index (1, 01, 12...):", width=300, height=50)
            fi_alignment_well_leading_zero = pn.widgets.Checkbox(name="Column leading zero (ie, \"01\"):", width=300, height=25)
            fi_alignment_forward_string = pn.widgets.TextInput(name="Forward Substring:", placeholder="Forward designation (ie, \"For\" or \"Promoter\")", width=300, height=50)
            fi_alignment_reverse_string = pn.widgets.TextInput(name="Reverse Substring:", placeholder="Reverse designation (ie, \"Rev\" or \"Terminator\")", width=300, height=50)
            fi_alignment_parent_entry = pn.widgets.Select(name="Parent Entry:", width=300, height=50)
            fi_alignment_input_module = pn.Column(
                pn.pane.HTML('<h3>Sequencing Data</h3>', width=300, height=30),
                fi_alignment_examples,
                fi_alignment_well_row_index,
                fi_alignment_well_column_index,
                fi_alignment_well_leading_zero,
                fi_alignment_forward_string,
                fi_alignment_reverse_string,
                fi_alignment_parent_entry,
                visible=False
            )

            fi_file_harvest_button = pn.widgets.Button(name="Please select a plate.", button_type='primary', disabled=True)
            fi_file_browser_module = pn.Row(
                pn.Column("<h3>File Import</h3>",fi_multi_upload, fi_file_harvest_button),
                pn.Row(fi_compound_input_module, fi_alignment_input_module)
            )
            file_input_pane = pn.Column(
                fi_plate_module,
                fi_file_browser_module,
            )
        except Exception as e:
            self.status_text.value = "DataInput_PaneAssembly" + str(e)
            self.debug_text.value += traceback.format_exc() + "\n\n"
        
        #Watchdogs and dynamic behavior
        #Plate creation and selection behavior
        def fi_plate_selector_watchdog(event):
            try:
                if event.name == 'value':
                    if event.new == 'New Plate':
                        fi_plate_name.visible=True
                        fi_add_plate_button.visible=True
                        fi_delete_plate_button.visible=False
                        fi_file_harvest_button.name = "Please select a plate."
                        fi_file_harvest_button.disabled = True
                    else:
                        fi_plate_name.visible=False
                        fi_add_plate_button.visible=False
                        fi_delete_plate_button.visible=True
                        fi_file_harvest_button.name = "Load data into %s"%event.new
                        fi_file_harvest_button.disabled = not(fi_multi_upload.progress_state == 1)
            except Exception as e:
                self.status_text.value = "fi_plate_selector_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        self.fi_plate_selector.param.watch(fi_plate_selector_watchdog, ['value'], onlychanged=False)
        
        def fi_add_plate_watchdog(event):
            try:
                if fi_plate_name.value in self.fi_plate_selector.options:
                    self.status_text.value = "%s already designated!"%fi_plate_name.value
                else:
                    if len(fi_plate_name.value) != 0:
                        self.status_text.value = f"Adding {fi_plate_name.value}"
                        library.add_plate(fi_plate_name.value)
                        self.fi_plate_selector.options = ['New Plate'] + list(library.plates)
            except Exception as e:
                self.status_text.value = "fi_add_plate_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        fi_add_plate_button.on_click(fi_add_plate_watchdog)
        
        def fi_delete_plate_watchdog(event):
            try:
                self.status_text.value = "Removing %s"%self.fi_plate_selector.value
                library.remove_plate(self.fi_plate_selector.value)
                self.fi_plate_selector.options = ['New Plate'] + list(library.plates)
            except Exception as e:
                self.status_text.value = "fi_delete_plate_watchdog: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
        fi_delete_plate_button.on_click(fi_delete_plate_watchdog)
        
        #File upload and parsing
        def fi_upload_state_changed(event):
            try:
                if event.new == 1:
                    #Setup our input view
                    fi_compound_input_module.visible = False
                    fi_alignment_input_module.visible = False
                    if fi_multi_upload.file_type == "Empower":
                        fi_compound_input_module.visible = True
                    elif fi_multi_upload.file_type == "FASTA":
                        fi_alignment_parent_entry.options = sorted([x[0] for x in fi_multi_upload.transfered_text])
                        id_list = [x[0] for x in fi_multi_upload.transfered_text[:min(5, len(fi_multi_upload.transfered_text))]]
                        max_len = max([len(x) for x in id_list])
                        example_string = "          "
                        for i in range(int(max_len/10)):
                            example_string += "%s         "%(i+1)
                        example_string += "\n"
                        for i in range(int(max_len/10)+1):
                            example_string += "0123456789"
                        example_string += "\n"
                        for i in range(len(id_list)):
                            example_string += "%s\n"%id_list[i]
                        fi_alignment_examples.object = example_string

                        fi_compound_input_module.visible = False
                        fi_alignment_input_module.visible = True
                        fi_alignment_parent_entry.visible = True
                    elif fi_multi_upload.file_type == "AB1":
                        id_list = fi_multi_upload.transfered_text[0][:min(5, len(fi_multi_upload.transfered_text[0]))]
                        max_len = max([len(x) for x in id_list])
                        example_string = "          "
                        for i in range(int(max_len/10)):
                            example_string += "%s         "%(i+1)
                        example_string += "\n"
                        for i in range(int(max_len/10)+1):
                            example_string += "0123456789"
                        example_string += "\n"
                        for i in range(len(id_list)):
                            example_string += "%s\n"%id_list[i]
                        fi_alignment_examples.object = example_string
                        fi_compound_input_module.visible = False
                        fi_alignment_input_module.visible = True
                        fi_alignment_parent_entry.visible = False
                    #Turn on the harvest button if a plate is selected
                    if self.fi_plate_selector.value == 'New Plate':
                        fi_file_harvest_button.disabled = True
                    else:
                        fi_file_harvest_button.disabled = False
                elif event.new == 2:
                    #Go through the received data and store it
                    plate = self.fi_plate_selector.value
                    if fi_multi_upload.file_type == "Empower":
                        for i in range(len(fi_multi_upload.transfered_text[0])):
                            sample_name = fi_multi_upload.transfered_text[0][i]
                            well = fi_multi_upload.transfered_text[1][i]
                            compound = fi_multi_upload.transfered_text[2][i]
                            source = fi_multi_upload.transfered_text[3][i]
                            time = np.array(fi_multi_upload.transfered_data[0][i], dtype=np.float32)
                            intensity = np.array(fi_multi_upload.transfered_data[1][i], dtype=np.float32)
                            if well not in library[plate]:
                                library[plate].add_well(well)
                            if compound not in library[plate][well]:
                                library[plate][well].add_chromatogram(compound, time, intensity, sample_name, source)
                                if compound not in library.compounds:
                                    library.compounds.append(compound)
                                if compound not in library[plate].compounds:
                                    library[plate].compounds.append(compound)
                    elif fi_multi_upload.file_type == "FASTA":
                        for i in range(len(fi_multi_upload.transfered_text)):
                            sample_name = fi_multi_upload.transfered_text[i][0]
                            seq = np.array(list(fi_multi_upload.transfered_text[i][1]))
                            if sample_name == fi_alignment_parent_entry.value:
                                library[plate].parent_alignment = seq
                            else:
                                well = sample_name[fi_alignment_well_row_index.value]
                                if fi_alignment_well_leading_zero.value:
                                    well += sample_name[fi_alignment_well_column_index.value:fi_alignment_well_column_index.value+2]
                                else:
                                    if sample_name[fi_alignment_well_column_index.value] == '1':
                                        if sample_name[fi_alignment_well_column_index.value+1].isnumeric():
                                            well += sample_name[fi_alignment_well_column_index.value:fi_alignment_well_column_index.value+2]
                                        else:
                                            well += '01'
                                    else:
                                        well += '0' + sample_name[fi_alignment_well_column_index.value]
                                read_dir = ""
                                if fi_alignment_forward_string.value in sample_name:
                                    read_dir = "For"
                                elif fi_alignment_reverse_string.value in sample_name:
                                    read_dir = "Rev"
                                else:
                                    raise ValueError(f"Direction element not found in {sample_name}")
                                if well not in library[plate]:
                                    library[plate].add_well(well)
                                if library[plate][well].sequencing == None:
                                    library[plate][well].add_sequencing()
                                library[plate][well].sequencing.add_alignment(seq, read_dir)
                    elif fi_multi_upload.file_type == "AB1":
                        for i in range(len(fi_multi_upload.transfered_text[0])):
                            sample_name = fi_multi_upload.transfered_text[0][i]
                            ab1_data = np.array(fi_multi_upload.transfered_data[i], dtype=np.uint16)
                            well = sample_name[fi_alignment_well_row_index.value]
                            if fi_alignment_well_leading_zero.value:
                                well += sample_name[fi_alignment_well_column_index.value:fi_alignment_well_column_index.value+2]
                            else:
                                if sample_name[fi_alignment_well_column_index.value] == '1':
                                    if sample_name[fi_alignment_well_column_index.value+1].isnumeric():
                                        well += sample_name[fi_alignment_well_column_index.value:fi_alignment_well_column_index.value+2]
                                    else:
                                        well += '01'
                                else:
                                    well += '0' + sample_name[fi_alignment_well_column_index.value]
                            read_dir = ""
                            if fi_alignment_forward_string.value in sample_name:
                                read_dir = "For"
                            elif fi_alignment_reverse_string.value in sample_name:
                                read_dir = "Rev"
                            else:
                                raise ValueError(f"Direction element not found in {sample_name}")
                            if well not in library[plate]:
                                library[plate].add_well(well)
                            if library[plate][well].sequencing == None:
                                library[plate][well].add_sequencing()
                            library[plate][well].sequencing.add_ab1_data(ab1_data, read_dir)
                    #Go back to idle
                    self.status_text.value = "Done loading data!"
                    fi_multi_upload.progress_state = 0
            except Exception as e:
                self.status_text.value = "fi_upload_state_changed: " + str(e)
                self.debug_text.value += traceback.format_exc() + "\n\n"
                
        fi_multi_upload.param.watch(fi_upload_state_changed, ['progress_state'], onlychanged=False)

        def fi_upload_status_changed(event):
            self.status_text.value = event.new
        fi_multi_upload.param.watch(fi_upload_status_changed, ['progress_status'], onlychanged=False)

        def fi_upload_progress_changed(event):
            self.progress_bar.value = event.new
        fi_multi_upload.param.watch(fi_upload_progress_changed, ['progress_percent'], onlychanged=False)

        def _file_harvesting(event):
            fi_multi_upload.harvest = not fi_multi_upload.harvest
        fi_file_harvest_button.on_click(_file_harvesting)        
        return file_input_pane
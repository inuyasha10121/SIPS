import panel as pn

import traceback

from .PlateClass import Library
from .global_utils import get_pn_id_token


sidebar_text = """### AReS

IN DEVELOPMENT
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
        tab_set.append(("AReS", self.pane_definition()))
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
        pane = pn.pane.Markdown("# AReS")
        return pane
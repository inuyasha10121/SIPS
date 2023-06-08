from panel.widgets.base import Widget
from . import dataselectiontable_model
import param

class DataSelectionTable(Widget):
    _widget_type = dataselectiontable_model.DataSelectionTable

    _rename = {
        "title": None,
        'name': 'name',
    }

    cells_per_page = param.Integer(default=10, bounds=(1,None))
    max_pages = param.Integer(default=3, bounds=(1,None))
    
    curr_page = param.Integer(default=0)
    
    possible_sources = param.List(default=[])
    wavelengths_3d = param.Dict(default={})
    
    compounds = param.List(default=[])
    sources = param.List(default=[])
    targets = param.List(default=[])
    
    update_sources = param.Boolean(default=False)
    
    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.compounds = ["" for i in range(self.cells_per_page * self.max_pages)]
        self.sources = ["" for i in range(self.cells_per_page * self.max_pages)]
        self.targets = ["" for i in range(self.cells_per_page * self.max_pages)]
    
    #def push_targets(self, new_targets: list, new_wavelengths: dict) -> None:
    #    self.possible_sources = new_targets
    #    self.wavelengths_3d = new_wavelengths
    #    self.curr_page = 0
    #    self.update_sources = not self.update_sources
from bokeh.core.properties import List, String, Bool, Int, Float, Dict
from bokeh.models import InputWidget

class DataSelectionTable(InputWidget):
    """Example implementation of a Custom Bokeh Model"""

    __implementation__ = "dataselectiontable.ts"
    
    cells_per_page = Int(default=10)
    max_pages = Int(default=3)
    
    curr_page = Int(default=0)
    
    possible_sources = List(String, default=[])
    wavelengths_3d = Dict(String, List(Float, default=[]), default={})
    
    compounds = List(String, default=[])
    sources = List(String, default=[])
    targets = List(String, default=[])
    
    update_sources = Bool(default=False)
    
    #def __init__(self, *args, **kwargs) -> None:
    #    super().__init__(*args, **kwargs)
from bokeh.core.properties import List, String, Bool, Int, Float, Dict
from bokeh.models import InputWidget

class FileProgressInput(InputWidget):
    """Example implementation of a Custom Bokeh Model"""

    __implementation__ = "fileprogressinput.ts"
    
    multiple = Bool(default=False)

    progress_state = Int(default=0)
    progress_percent = Float(default=0)
    progress_status = String(default="")

    file_type = String(default="")
    #file_params = List(String(default=""), default=[])
    #file_wavelengths = Dict(String(default=""), List(Float, default=[]), default={})

    harvest = Bool(default=False)
    transfered_text = List(List(String(default=""), default=[]), default=[])
    transfered_data = List(List(List(Float(default=0), default=[]), default=[]), default=[])
    #transfered_data = List(List(String(default=""), default=[]), default=[[]])
    #transfered_data = List(List(Float(default=0), default=[]), default=[[]])
    #file_content = String(default = "")
    #mime_type = String(default = "")
    #accept = String(default = "")
    #is_loading = Bool(default=False)
    #num_files = Int(default=0)
    #load_progress = Int(default=0)
    #
    #file_names = List(String(default=""), default=[""])
    #file_contents = List(String(default=""), default=[""])
    #mime_types = List(String(default=""), default=[""])
    
    #def __init__(self, *args, **kwargs) -> None:
    #    super().__init__(*args, **kwargs)
    #    print(f"BK args: {args}")
    #    print(f"BK kwargs: {list(kwargs)}")
    #    if 'name' in kwargs:
    #        print(kwargs['name'])
    #    self.on_change("is_loading", self._reset_lists)
    #    self.on_change("file_name", self._file_name_transfered)
    #    self.on_change("file_content", self._file_content_transfered)
    #    self.on_change("mime_type", self._mime_type_transfered)
    #
    #def _reset_lists(self, attr, old, new):
    #    if new:
    #        self.file_names = []
    #        self.file_contents = []
    #        self.mime_types = []
    #
    #def _file_name_transfered(self, attr, old, new):
    #    self.file_names.append(new)
    #
    #def _file_content_transfered(self, attr, old, new):
    #    self.file_contents.append(new)
    #
    #def _mime_type_transfered(self, attr, old, new):
    #    self.mime_types.append(new)
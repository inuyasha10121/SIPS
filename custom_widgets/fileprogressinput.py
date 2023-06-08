from panel.widgets.base import Widget
from . import fileprogressinput_model
import param

class FileProgressInput(Widget):
    _widget_type = fileprogressinput_model.FileProgressInput

    _rename = {
        "title": None,
        'name': 'name',
    }

    multiple = param.Boolean(default=False)

    progress_state = param.Number(default=0)
    progress_percent = param.Number(default=0)
    progress_status = param.String(default="")

    file_type = param.String(default="")
    #file_params = param.List(item_type=str, default=[])
    #file_wavelengths = param.Dict(default={})

    harvest = param.Boolean(default=False)
    transfered_text = param.List(item_type=list)
    transfered_data = param.List(item_type=list)

    #transfered_data = param.List(item_type=param.List(item_type=[
    #    param.String(default=""),
    #    param.String(default=""),
    #    param.String(default=""),
    #    param.String(default=""),
    #    param.List(item_type=param.Number(default=0), default=[]),
    #    param.List(item_type=param.Number(default=0), default=[])
    #], default=["", "", "", "", [], []]), default=[])

    #file_name = param.String(default = "")
    #file_content = param.String(default = "")
    #mime_type = param.String(default = "")
    #accept = param.String(default = "")
    #is_loading = param.Boolean(default=False)
    #num_files = param.Integer(default=0)
    #load_progress = param.Integer(default=0)
    #
    #file_names = param.List(item_type=str, default=[""])
    #file_contents = param.List(item_type=str, default=[""])
    #mime_types = param.List(item_type=str, default=[""])

    #def __init__(self, *args, **kwargs) -> None:
    #    super().__init__(*args, **kwargs)
    #    print(f"PN args: {args}")
    #    print(f"PN kwargs: {list(kwargs)}")
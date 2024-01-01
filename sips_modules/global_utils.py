import panel as pn
import hashlib
from bokeh.server.contexts import BokehSessionContext

def get_pn_id_token() -> str:
    """Returns id token from cookie"""
    hash_obj = hashlib.md5()
    hash_obj.update(pn.state.cookies['id_token'].encode('utf-8'))
    return hash_obj.hexdigest()[:16]
    

def get_id_token(session_context: BokehSessionContext) -> str:
    """Returns id token from cookie"""
    hash_obj = hashlib.md5()
    hash_obj.update(session_context.request.cookies['id_token'].encode('utf-8'))
    return hash_obj.hexdigest()[:16]
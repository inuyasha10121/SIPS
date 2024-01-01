import os
import time
import importlib
import traceback

import pickle
import json

import holoviews as hv
hv.extension('bokeh')

import panel as pn
pn.extension()

from bokeh.server.contexts import BokehSessionContext

from sips_modules.global_utils import get_id_token, get_pn_id_token
from sips_modules.PlateClass import Library
#Load config and setup environment
with open('./assets/config.json', 'r') as f:
    config = json.load(f)
os.environ["BOKEH_NODEJS_PATH"] = config["nodejs_path"]

status_text = pn.widgets.TextInput(disabled=True, placeholder=f"Welcome to SIPS {config['sips_version']}", width=500)

def SIPS():
    welcome_markdown_text = """
    This software is designed for processing and analyzing SUbstrate Multiplexed Screening (SUMS) data to help better understand underlying trends and select variants for further study.  
    If you have any questions, comments, feature requests, or would like to improve/expand the program, please contact the developer via the following methods:

    E-mail: jmellis4@wisc.edu

    [Github](https://github.com/inuyasha10121/SIPS)

    To learn more about the underlying process, please visit the documentation page:

    ### Planned Features:
    * **General**
        * Improved loading display
        * Multithreaded processing for increased speed
    * **File Loading**
        * Folder dropping
    * **MS-FIT**
        * Peak drift correction
        * Show all integrated peak overlay
        * Split peak detection
    * **AReS**
        * "List mutations" function for analyzing error-prone libraries
    * **Processing**
        * Plot data exporting
        * Violin plots for activity distribution statistics
        * Simple modelling techniques (Linear/Logistic regression, SVM, etc.)

    ### Citations:
    * "Automating LC–MS/MS mass chromatogram quantification: Wavelet transform based peak 
    detection and automated estimation of peak boundaries and signal-to-noise ratio using 
    signal processing methods" DOI: 10.1016/j.bspc.2021.103211
    * "A Quantitative Index of Substrate Promiscuity" DOI: 10.1021/bi701448p


    *Drink deep of the Pierian spring*
    """
    welcome_sidebar = """<h2>Instructions will be displayed here</h2>"""

    library: Library = pn.state.cache['id_tokens'][get_pn_id_token()]['library']

    #Setup sidebar info
    sidebar_info = pn.pane.Markdown(welcome_sidebar)

    #Setup debugging view
    debug_text = pn.widgets.TextAreaInput(width=800, height=800)
    test_button = pn.widgets.Button(name='Test')
    library_tree_button = pn.widgets.Button(name='Library Tree')
    check_bin_button = pn.widgets.Button(name='Check .bins')
    load_bin_button = pn.widgets.Button(name='Load .bin')
    save_bin_button = pn.widgets.Button(name='Save .bin')
    bin_selection = pn.widgets.Select()
    bin_save_name = pn.widgets.TextInput()

    check_pkl_button = pn.widgets.Button(name="Check .pkls")
    load_pkl_button = pn.widgets.Button(name="Load .pkl")
    save_pkl_button = pn.widgets.Button(name="Save .pkl")
    pkl_selection = pn.widgets.Select()
    pkl_save_name = pn.widgets.TextInput()

    load_direct_button = pn.widgets.Button(name="Load direct")

    def test_button_callback(event):
        print(get_pn_id_token())
        print(pn.state.cache['id_tokens'])
        for x in ['PLATE1', 'PLATE2', 'PLATE3']:
            pn.state.cache['id_tokens'][get_pn_id_token()]['library'].add_plate(x)
    test_button.on_click(test_button_callback)

    def library_tree_callback(event):
        print(pn.state.cache['id_tokens'])
        debug_text.value += f"{pn.state.cache['id_tokens'][get_pn_id_token()]['library'].get_tree()}\n"
    library_tree_button.on_click(library_tree_callback)

    def scan_bin_callback(event):
        try:
            bin_selection.options = [x for x in os.listdir('../archives/') if x.endswith('.bin')]
        except Exception as e:
            status_text.value = "scan_bin_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    check_bin_button.on_click(scan_bin_callback)

    def save_bin_button_callback(event):
        try:
            filename = "test.bin"
            if bin_save_name.value != "":
                filename = bin_save_name.value
                if not filename.endswith(".bin"):
                    filename += ".bin"
            library.save_binary(f"../archives/{filename}")
            status_text.value = 'Done saving!'
        except Exception as e:
            status_text.value = "save_bin_button_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    save_bin_button.on_click(save_bin_button_callback)

    def load_bin_callback(event):
        try:
            library.load_binary(f"../archives/{bin_selection.value}")
            #TODO: Put code here to populate the selector drop downs appropriately.
            status_text.value = 'Done loading!'
        except Exception as e:
            status_text.value = "load_bin_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    load_bin_button.on_click(load_bin_callback)


    def scan_pkl_callback(event):
        try:
            pkl_selection.options = [x for x in os.listdir('../archives/') if x.endswith('.pkl')]
        except Exception as e:
            status_text.value = "scan_pkl_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    check_pkl_button.on_click(scan_pkl_callback)

    def save_pkl_button_callback(event):
        try:
            filename = "test.pkl"
            if pkl_save_name.value != "":
                filename = pkl_save_name.value
                if not filename.endswith(".pkl"):
                    filename += ".pkl"
            with open(f"../archives/{filename}", 'wb') as f:
                pickle.dump(library, f)
            status_text.value = 'Done saving!'
        except Exception as e:
            status_text.value = "save_pkl_button_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    save_pkl_button.on_click(save_pkl_button_callback)

    def load_pkl_callback(event):
        try:
            with open(f"../archives/{pkl_selection.value}", 'rb') as f:
                library.set_cache_lib(pickle.load(f))
            status_text.value = 'Done loading!'
        except Exception as e:
            status_text.value = "load_pkl_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    load_pkl_button.on_click(load_pkl_callback)

    def load_direct_button_callback(event):
        try:
            ret = "LIBRARY\n"
            for plate in library:
                ret += f"  {plate}\n"
                for well in library[plate]:
                    ret += f"    {well}\n"
                    for target in library[plate][well].chromatograms:
                        ret += f"      {target}\n"
            debug_text.value = ret
        except Exception as e:
            status_text.value = "load_bin_callback: " + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    load_direct_button.on_click(load_direct_button_callback)


    admin_box = pn.Column(
        pn.Row(library_tree_button, test_button),
        pn.Row(check_bin_button, bin_selection, load_bin_button),
        pn.Row(bin_save_name, save_bin_button),
        pn.Row(check_pkl_button, pkl_selection, load_pkl_button),
        pn.Row(pkl_save_name, save_pkl_button),
        load_direct_button,
        visible=False
    )

    debug_box = pn.Column(
        pn.layout.Divider(),
        admin_box,
        pn.pane.Markdown("Debug output:"),
        debug_text,
        visible=True
    )

    #Setup welcome pane
    welcome_pane = pn.Column(
        pn.pane.Markdown("<h1>Welcome to SIPS!</h1>"),
        pn.pane.PNG("./assets/SIPSImage.png", width=150),
        pn.pane.Markdown(welcome_markdown_text), width=800
    )

    tab_set = pn.Tabs(
        ('Info', welcome_pane),
    dynamic=True)

    main_display = pn.Column(
        tab_set,
        debug_box,
    )

    def tab_selection_callback(event):
        try:
            if event.name == "active":
                if event.new == 0: #Info
                    sidebar_info.object = welcome_sidebar
        except Exception as e:
            status_text.value = "tab_selection_callback" + str(e)
            debug_text.value += traceback.format_exc() + "\n\n"
    tab_set.param.watch(tab_selection_callback, ['active'])

    #Setup status bar
    logout_button = pn.widgets.Button(name='Logout', button_type='danger', align=('end', 'center'))
    def logout_button_callback(event):
        pn.state.location.pathname = pn.state.location.pathname.split("/")[0] + "/logout"
        pn.state.location.reload = True
    logout_button.on_click(logout_button_callback)
    progress_bar = pn.indicators.Progress(name='Progress', value=0, bar_color='primary', align=('center', 'center'))
    status_bar = pn.Row(status_text, progress_bar, logout_button)

    #Load modules
    sips_modules = [x for x in os.listdir('./sips_modules') if x.endswith(".py")]
    sips_modules = [x[:-3] for x in sips_modules if x != "__init__.py"]
    module_instances = []
    for i, m in enumerate(config["modules"]):
        if os.path.exists(f"./sips_modules/{m}.py"):
            module_import = importlib.import_module(f"sips_modules.{m}")
            module_instances.append(module_import.module_class(i+1, status_text, progress_bar, debug_text))
            module_instances[-1].bind_tab(tab_set, sidebar_info)
        else:
            debug_text.value += f"{m} MODULE MISSING\n"

    #Setup Bootstrap display
    bootstrap = pn.template.BootstrapTemplate(title='SIPS %s'%config['sips_version'])

    bootstrap.sidebar.append(sidebar_info)

    bootstrap.main.append(main_display)

    bootstrap.header.append(status_bar)

    #Debug view setup
    if (pn.state.user == 'debug'):
        admin_box.visible = True
    
        #Current module refactoring
        module_import = importlib.import_module(f"sips_modules.AReS")
        module_instances.append(module_import.module_class(len(module_instances)+1, status_text, progress_bar, debug_text))
        module_instances[-1].bind_tab(tab_set, sidebar_info)
    
        #Experimental tab addition
        module_import = importlib.import_module(f"sips_modules.Experimental")
        module_instances.append(module_import.module_class(len(module_instances)+1, status_text, progress_bar, debug_text))
        module_instances[-1].bind_tab(tab_set, sidebar_info)
    
    return bootstrap

def on_session_created_callback(session_context: BokehSessionContext):
    id_token = get_id_token(session_context)
    print(f"CREATED: {id_token}")
    if id_token not in pn.state.cache['id_tokens'].keys():
        pn.state.cache['id_tokens'][id_token] = {
            'lifetime': time.time() + 1000000, #Save tokens for approximately one week
            'library': Library()
        }
        status_text.value = "Created new library"
    else:
        status_text.value = "Loaded previous state"
        #Refresh token lifetime
        pn.state.cache['id_tokens'][id_token]['lifetime'] = time.time() + 1000000
        #TODO: Eventually, load library data here
pn.state.on_session_created(on_session_created_callback)

def on_session_destroyed_callback(session_context: BokehSessionContext):
    id_token = get_id_token(session_context)
    print(f"DESTROYED: {id_token}")
    #TODO: Eventually, store library data here in user folder
pn.state.on_session_destroyed(on_session_destroyed_callback)

#Server launch initialization
pn.state.cache['id_tokens'] = {}

app = pn.serve(
    {"SIPS": SIPS},
    port=9999,
    websocket_origin=os.getenv('ALLOWED_ORIGINS').split(','),
    static_dirs={'assets': './assets'},
    basic_auth='./assets/credentials.json',
    cookie_secret=os.getenv('COOKIE_SECRET'),
    basic_login_template='./assets/login_page.html',
    #websocket_max_message_size=1000000000,
    #warm=True,
    autoreload=True,
    title="SIPS",
    show=False,
    start=True,
)
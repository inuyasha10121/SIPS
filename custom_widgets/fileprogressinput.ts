//Gonna build this like a state machine, because I am so fucking lost on how to do a parallel setv operation that doesn't choke the app
//Hopefully, this way things are modular enough that I can plug in new state blocks and speed things up in the future
//State 0 (Idle): Waiting for user input.  Advances on user uploading files (onchange)
//State 1 (Preliminary read): Scans the files and pulls out relevant information that will need to be displayed to the user for input harvesting.
//State 2 (Prelim done): Signal to user that the preliminary read is done and setup the input interface accordingly.  Advances on user "harvest" input
//State 3 (Harvest): Actually harvest the data and package it for transfer
//State 4 (Transfer): Transfer the data to the server.  Prompt the user that this will take a while.  This loops back to state 0 after.

import * as p from "core/properties"
import {div, input, label} from "core/dom"
import {InputWidget, InputWidgetView} from "models/widgets/input_widget"

interface EmpowerFile extends File {
    tag: string
    sample_name: string
    well: string
    wavelengths: number[]
    content3d: boolean

}

class WorkerPool {
    max_workers: number
    worker_pool: Worker[]
    constructor(){
        this.max_workers = Math.max(navigator.hardwareConcurrency, 4);
        this.worker_pool = [];
    }
    _init_pool(worker_func: Function, num_tasks: number): void {
        const func_str = worker_func.toString();
        const funcBody = func_str.substring( func_str.indexOf( '{' ) + 1, func_str.lastIndexOf( '}' ) );
        const workerSourceURL = URL.createObjectURL( new Blob( [ funcBody ] ) );
        const num_workers = Math.min(num_tasks, this.max_workers)
        for (let i = 0; i < num_workers; i++){
            this.worker_pool.push(new Worker(workerSourceURL))
        }
    }
    _clear_pool(): void {
        this.worker_pool.forEach((worker) => {
            worker.terminate()
        })
        this.worker_pool = []
    }
    _task_worker(worker: Worker, input_data: any): Promise<any> {
        return new Promise((resolve, reject) => {
            worker.addEventListener('message', (event) => {
                resolve(event.data)
            })
            worker.addEventListener('error', (event) => {
                reject(event.error)
            })
            worker.postMessage(input_data)
        })
    }
    async task_pool(worker_func: Function, task_arr: Array<any>, additional_data: any[]|null = null): Promise<any[]> {
        this._init_pool(worker_func, task_arr.length)
        const tasks = this.worker_pool.map((worker, index) => {
            const task_data = task_arr.filter((_, i) => i % this.worker_pool.length === index)
            if (additional_data != null){
                return this._task_worker(worker, task_data.concat(additional_data))
            } else {
                return this._task_worker(worker, task_data)
            }
            
        })
        let final_results: any[] = []
        try {
            const results = await Promise.all(tasks)
            final_results = results.flat()
        } finally {
            this._clear_pool()
            return final_results
        }
    }
}

export class FileProgressInputView extends InputWidgetView {
    declare model: FileProgressInput
    input_el: HTMLInputElement
    div_el: HTMLDivElement
    num_files: number
    current_progress: number

    worker_pool: WorkerPool

    connect_signals(): void {
        super.connect_signals()

        this.connect(this.model.properties.harvest.change, () => {
            this.current_progress = 0;
            this.harvest_data();
        });
    }

    override render(): void {
        super.render()
        
        const self = this
        if (this.worker_pool == null){
            this.worker_pool = new WorkerPool()
        }
        if (this.num_files == null){
            this.num_files = 0
        }
        if (this.current_progress == null){
            this.current_progress = 0
        }

        if (this.input_el == null) {
            this.input_el = input({
                type: "file",
                multiple: this.model.multiple,
                hidden: true
            });
            
            this.input_el.addEventListener("change", () => {
                const { files } = self.input_el;
                if (files != null) {
                    if (files.length > 0){
                        self.model.setv({
                            progress_status: "File upload detected. Preprocessing data...",
                        });
                        self.num_files = files.length;
                        self.current_progress = 0;
                        self.determine_harvest_params(files);
                    } else {
                        self.model.setv({
                            progress_status: "Please select some files to upload",
                        });
                    }
                }
            });
        }

        if (this.div_el == null) {
            
            const label_el = label({
                style: {
                    fontWeight: "bold",
                    pointerEvents: "none"
                },
            }, "Drag/drop files, or click to open a browser")

            this.div_el = div({
                style: {
                    border: "5px dashed #0072B5",
                    width: `${this.model.width}px`,
                    height: `${this.model.height}px`,
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center"
                },
            }, [this.input_el, label_el])

            function hover_style(flag: boolean): void{
                if (flag){
                    label_el.innerText = "Drop to process files"
                    self.div_el.style.backgroundColor = "lightgray"
                    self.div_el.style.borderStyle = 'solid'
                } else {
                    label_el.innerText = "Drag/drop files, or click to open a browser"
                    self.div_el.style.backgroundColor = ""
                    self.div_el.style.borderStyle = 'dashed'
                }
            }
            
            this.div_el.addEventListener("dragover", (event) => {
                event.preventDefault();
            });

            this.div_el.addEventListener("dragenter", (event) => {
                event.preventDefault()
                hover_style(true)
            });

            this.div_el.addEventListener("dragleave", (event) => {
                event.preventDefault()
                hover_style(false)
            });
            
            this.div_el.addEventListener("drop", (event) => {
                event.preventDefault()
                hover_style(false)
                if (event.dataTransfer != null){
                    if (event.dataTransfer.files.length > 0){
                        self.input_el.files = event.dataTransfer.files
                        const changeEvent = new Event("change", { bubbles: true });
                        self.input_el.dispatchEvent(changeEvent);
                    }
                }
            });

            this.div_el.addEventListener("mouseup", (event) => {
                event.preventDefault()
                self.input_el.click()
            });

            this.group_el.appendChild(this.div_el);
        }
    }

    _read_file_text(file: File): Promise<[File, string]> {
        return new Promise<[File, string]>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => {
                const {result} = reader
                if (result != null) {
                    //this.current_progress += 1 / (this.num_files * 2)
                    //this.model.setv({
                    //    progress_percent: Math.round(100 * this.current_progress)
                    //})
                    //console.log("File read")
                    resolve([file, result as string])
                } else {
                    reject(reader.error ?? new Error(`unable to read '${file.name}'`))
                }
            }
            reader.onerror = () => {
                reject(new Error(`Error reading '${file.name}'`));
            }
            reader.readAsText(file);
        })
    }

    determine_harvest_params(files: FileList): void{
        //Make sure all the file extensions are the same
        const ext = files[0].name.split('.').pop()
        for (let i = 1; i < files.length; i++){
            let test_ext = files[i].name.split('.').pop()
            if (ext !== files[i].name.split('.').pop()) {
                this.model.setv({
                    progress_status: `Files must all be of same type (found ${ext} and ${test_ext})`
                })
                return
            }
        }
        //Choose what to do based on file type
        switch (ext){
            case 'arw':
                function _extract_empower_params(file: EmpowerFile, content: string): Promise<EmpowerFile>{
                    return new Promise<EmpowerFile>((resolve, reject) => {
                        if (content != null){
                            //const self = this
                            function progress_resolve(file: EmpowerFile): void{
                                //self.current_progress += 1 / (self.num_files * 2)
                                //self.model.setv({
                                //    progress_percent: Math.round(100 * self.current_progress)
                                //})
                                //console.log('Params parsed')
                                resolve(file)
                            }
                            //First, check to see if we have the necessary information in the header
                            let content_lines = content.split(/[\x0D\x0a]+/g)
                            const header_labels = (content_lines[0].match(/(?:"[^"]*"|\S+)/g) as RegExpMatchArray)
                            const header_content = (content_lines[1].match(/(?:"[^"]*"|\S+)/g) as RegExpMatchArray)
            
                            const channel_ind = header_labels.indexOf("\"Channel Description\"")
                            if (channel_ind == -1){
                                reject(new Error(`${file.name} is missing a channel description`))
                            }
                            const channel_desc = header_content[channel_ind]
            
                            const vial_ind = header_labels.indexOf("\"Vial\"")
                            if (vial_ind == -1){
                                reject(new Error(`${file.name} is missing a vial ID`))
                            }
                            let vial_bits = header_content[vial_ind].slice(2).split(',')
                            vial_bits[1] = vial_bits[1].padStart(2, '0')
                            file.well = vial_bits[0] + vial_bits[1]
            
                            const sample_ind = header_labels.indexOf("\"SampleName\"")
                            if (sample_ind == -1) {
                                file.sample_name = ""
                            } else {
                                file.sample_name = header_content[sample_ind].slice(1, -1)
                            }
                            //Now, extract out the channel information
                            //Possible formats:
                            //"1: QDa Positive(+) Scan (150.00-750.00)Da, Centroid, CV=15"
                            //"2: QDa Negative(-) Scan (150.00-750.00)Da, Centroid, CV=15"
                            //"PDA Spectrum (210-400)nm"
                            //"2: QDa Positive(+) SIR Ch1 202.00 Da, CV=15"
                            //"PDA Ch2 340nm@4.8nm"
            
                            if (channel_desc.includes('QDa')){
                                if (channel_desc.includes('Scan')) {
                                    file.wavelengths = content_lines[2].split(/\s/g).slice(1).map(parseFloat);
                                    file.content3d = true
                                    if (channel_desc.includes('Positive')){
                                        file.tag = '(+)MS Scan'
                                        progress_resolve(file)
                                    } else if (channel_desc.includes('Negative')){
                                        file.tag = '(-)MS Scan'
                                        progress_resolve(file)
                                    }
                                } else if (channel_desc.includes('SIR')){
                                    file.content3d = false
                                    file.wavelengths = []
                                    const desc_split = channel_desc.split(/[ ,]+/g)
                                    const sir_mz = desc_split[desc_split.indexOf('Da')-1]
                                    if (channel_desc.includes('Positive')){
                                        file.tag = `(+)SIR ${sir_mz} m/z`
                                        progress_resolve(file)
                                    } else if (channel_desc.includes('Negative')){
                                        file.tag = `(-)SIR ${sir_mz} m/z`
                                        progress_resolve(file)
                                    }
                                } else {
                                    reject(new Error(`${file.name} has a malformed MS description`))
                                }
                            } else if (channel_desc.includes('PDA')) {
                                if (channel_desc.includes('Spectrum')) {
                                    file.wavelengths = content_lines[2].split(/\s/g).slice(1).map(parseFloat);
                                    file.content3d = false
                                    file.tag = `PDA Scan`
                                    progress_resolve(file)
                                } else if (channel_desc.includes('@')) {
                                    file.content3d = false
                                    file.wavelengths = []
                                    const desc_split = channel_desc.split(/[ ,]+/g)
                                    const wl_ind = desc_split.findIndex(el => el.includes('@'))
                                    const wl = desc_split[wl_ind].split('@')[0]
                                    file.tag = wl
                                    progress_resolve(file)
                                } else {
                                    reject(new Error(`${file.name} has a malformed PDA description`))
                                }
                            }
                            reject(new Error(`${file.name} has unknown data description: ${channel_desc}`))
                        } else {
                            reject(new Error(`Data from ${file.name} was not passed!`))
                        }
                        
                    })
                }

                Promise.all(Array.from(files).map(async (file) => {
                    return await this._read_file_text(file)
                })).then((read_files) => {
                    Promise.all(read_files.map(async ([file, content]) => {
                        return await _extract_empower_params(file as EmpowerFile, content)
                    })).then((extractedValues: EmpowerFile[]) => {
                        var unique_entries = new Set()
                        var wavelengths: { [key: string]: Set<number> | number[]} = {};
                        extractedValues.forEach((file: EmpowerFile) => {
                            if (file.tag.includes('Scan')){
                                if (unique_entries.has(file.tag)){
                                    wavelengths[file.tag] = new Set([...wavelengths[file.tag], ...file.wavelengths]);
                                } else {
                                    unique_entries.add(file.tag)
                                    wavelengths[file.tag] = new Set(file.wavelengths)
                                }
                            } else {
                                unique_entries.add(file.tag)
                            }
                        });
                        for (const key in wavelengths) {
                            if (wavelengths.hasOwnProperty(key)) {
                                const set = wavelengths[key];
                                // Convert the set to an array
                                const array = [...set]; // or Array.from(set)
                                // Update the value in the dictionary
                                wavelengths[key] = array;
                            }
                        }
                        //Move things over to the data selection table
                        if (this.model.document != null){
                            let dst_model = this.model.document.get_model_by_name('bk_fi_target_table')
                            if (dst_model != null){
                                dst_model.setv({
                                    possible_sources: Array.from(unique_entries),
                                    wavelengths_3d: wavelengths,
                                    curr_page: 0,
                                    update_sources: !dst_model.attributes.update_sources
                                })
                            }
                        }
                        this.model.setv({
                            file_type: 'Empower',
                            //file_params: Array.from(unique_entries),
                            //file_wavelengths: wavelengths,
                            progress_state: 1,
                            progress_percent: -1,
                            progress_status: 'Parameters extracted!  Please input harvesting info.'
                        })
                    })
                })
                break
            case 'ab1':
                //This is fluoresences data from a sequencing read, to be used in AReS
                break
            case 'fasta':
                //This is alignment data from a sequencing run, to be used in AReS
                break
            case 'bin':
                //This is an archival file from the software 
                break
            default:
                this.model.setv({
                    progress_state: 0,
                    progress_status: `Unknown extension: ${ext}`
                })
                break
        }
        return
    }

    harvest_data(): void {
        //Extract out everything the user specified from the data selection table
        if (this.model.document != null){
            let dst_model = this.model.document.get_model_by_name('bk_fi_target_table')
            if (dst_model != null){
                //console.log("Pulling dst values")
                let dst_compounds = (dst_model.attributes.compounds as string[])
                let dst_sources = (dst_model.attributes.sources as string[])
                let dst_targets = (dst_model.attributes.targets as string[])
                let harvest_compounds = [] as string[]
                let harvest_sources = [] as string[]
                let harvest_targets = [] as number[]
                for(let i = 0; i < ((dst_model.attributes.max_pages as number) * (dst_model.attributes.cells_per_page as number)); i++){
                    let compound = dst_compounds[i]
                    if (compound != ""){
                        let source = dst_sources[i]
                        if (source.includes("Scan")){
                            //3D data
                            let target = dst_targets[i]
                            if (target != ""){
                                harvest_compounds.push(compound)
                                harvest_sources.push(source)
                                harvest_targets.push(parseFloat(target))
                            }
                        } else {
                            //2D data
                            harvest_compounds.push(compound)
                            harvest_sources.push(source)
                            harvest_targets.push(0)
                        }
                    }
                }
                //Now, we can read the files
                this.model.setv({
                    progress_percent: 0,
                    progress_status: 'Harvesting requested data...'
                })
                //console.log("Parsing files")

                function harvest_empower_data(){
                    async function _read_file_text(file: File): Promise<string> {
                        return new Promise<string>((resolve, reject) => {
                            const reader = new FileReader()
                            reader.onload = () => {
                                const {result} = reader
                                if (result != null) {
                                    //this.current_progress += 1 / (this.num_files * 2)
                                    //this.model.setv({
                                    //    progress_percent: Math.round(100 * this.current_progress)
                                    //})
                                    //console.log(`File read: ${file.name}`)
                                    resolve(result as string)
                                } else {
                                    reject(reader.error ?? new Error(`unable to read '${file.name}'`))
                                }
                            }
                            reader.onerror = () => {
                                reject(new Error(`Error reading '${file.name}'`));
                            }
                            reader.readAsText(file);
                        })
                    }
                    
                    async function _harvest_empower_file(content: string, harvest_compounds: string[], harvest_sources: string[], harvest_targets: number[]): Promise<[string, string, string, string, number[], number[]][]> {
                        return new Promise((resolve) => {
                            //const self = this
                            function progress_resolve(parsed_data: [string, string, string, string, number[], number[]][]): void{
                                //self.current_progress += 1 / (self.num_files * 2)
                                //self.model.setv({
                                //    progress_percent: Math.round(100 * self.current_progress)
                                //})
                                //console.log("Data harvested")
                                resolve(parsed_data)
                            }
                
                            function parse_data(array: string[]): number[][] {
                                let values = array.map(line => {
                                    return line.split(/\s/g).map(num => {
                                      return parseFloat(num)
                                  })
                                })
                                return values.map((_, colIndex) => values.map(row => row[colIndex]));
                            }
                            
                            //Re-extract our relevant parameters from the header
                            //First, check to see if we have the necessary information in the header
                            let content_lines = content.split(/[\x0D\x0a]+/g)
                            const header_labels = (content_lines[0].match(/(?:"[^"]*"|\S+)/g) as RegExpMatchArray)
                            const header_content = (content_lines[1].match(/(?:"[^"]*"|\S+)/g) as RegExpMatchArray)
                            
                            const vial_ind = header_labels.indexOf("\"Vial\"")
                            let vial_bits = header_content[vial_ind].slice(3, -1).split(',')
                            vial_bits[1] = vial_bits[1].padStart(2, '0')
                            const well = vial_bits[0] + vial_bits[1]
                            
                            let sample_name = ""
                            const sample_ind = header_labels.indexOf("\"SampleName\"")
                            if (sample_ind != -1) {
                                sample_name = header_content[sample_ind].slice(1, -1)
                            }
                            
                            const channel_ind = header_labels.indexOf("\"Channel Description\"")
                            const channel_desc = header_content[channel_ind]

                            let tag = ""
                            let wavelengths: number[] = []
                            if (channel_desc.includes('QDa')){
                                if (channel_desc.includes('Scan')) {
                                    wavelengths = content_lines[2].split(/\s/g).slice(1).map(parseFloat);
                                    if (channel_desc.includes('Positive')){
                                        tag = '(+)MS Scan'
                                    } else if (channel_desc.includes('Negative')){
                                        tag = '(-)MS Scan'
                                    }
                                } else if (channel_desc.includes('SIR')){
                                    const desc_split = channel_desc.split(/[ ,]+/g)
                                    const sir_mz = desc_split[desc_split.indexOf('Da')-1]
                                    if (channel_desc.includes('Positive')){
                                        tag = `(+)SIR ${sir_mz} m/z`
                                    } else if (channel_desc.includes('Negative')){
                                        tag = `(-)SIR ${sir_mz} m/z`
                                    }
                                }
                            } else if (channel_desc.includes('PDA')) {
                                if (channel_desc.includes('Spectrum')) {
                                    wavelengths = content_lines[2].split(/\s/g).slice(1).map(parseFloat);
                                    tag = `PDA Scan`
                                } else if (channel_desc.includes('@')) {
                                    const desc_split = channel_desc.split(/[ ,]+/g)
                                    const wl_ind = desc_split.findIndex(el => el.includes('@'))
                                    const wl = desc_split[wl_ind].split('@')[0]
                                    tag = wl
                                }
                            }
                            
                            //Go through all our harvested sources
                            let results: [string, string, string, string, number[], number[]][] = []
                            for (let i = 0; i < harvest_sources.length; i++){
                                //Check if the file source matches
                                if (harvest_sources[i] == tag){
                                    let compound = harvest_compounds[i]
                                    //Check for 3D or 2D data
                                    if (wavelengths.length > 0){
                                        let parsed_content = parse_data(content_lines.slice(4, -1))
                                        let target = harvest_targets[i]
                                        //Make our tag more descriptive
                                        let new_tag = ""
                                        if (tag.includes('MS')){
                                            new_tag = `${tag.substring(0, 3)}XIC ${target} m/z`
                                        } else {
                                            new_tag = `XAC ${target} nm`
                                        }
                                        //Find the closest wavelength or m/z to the target
                                        function find_closest(arr: number[], target: number): number{
                                            let diff = Math.abs(arr[0] - target)
                                            let best = 0
                                            for (let i = 1; i < arr.length; i++){
                                                if (Math.abs(arr[i] - target) < diff){
                                                    best = i
                                                }
                                            }
                                            return best
                                        }
                                        let closest_wl_ind = find_closest(wavelengths, target)
                                        results.push([sample_name, well, compound, new_tag, parsed_content[0], parsed_content[closest_wl_ind]])
                                    } else {
                                        let parsed_content = parse_data(content_lines.slice(2, -1))
                                        //Easy push
                                        results.push([sample_name, well, compound, tag, parsed_content[0], parsed_content[1]])
                                    }
                                }
                            }
                            progress_resolve(results)
                        });
                    }
                    
                    self.addEventListener('message', async (event) => {
                        const files: EmpowerFile[] = event.data.slice(0,-3)
                        const harvest_compounds: string[] = event.data[event.data.length-3]
                        const harvest_sources: string[] = event.data[event.data.length-2]
                        const harvest_targets: number[] = event.data[event.data.length-1]
                        Promise.all(
                            files.map(async (file: EmpowerFile) => {
                                const content = await _read_file_text(file)
                                const parsed_content = await _harvest_empower_file(content, harvest_compounds, harvest_sources, harvest_targets)
                                return parsed_content
                            })
                        ).then((extractedValues: [string, string, string, string, number[], number[]][][]) => {
                            self.postMessage(extractedValues)
                        })
                    })
                }
                this.worker_pool.task_pool(harvest_empower_data, Array.from(this.input_el.files as FileList), [harvest_compounds, harvest_sources, harvest_targets]).then((result: ([string, string, string, string, number[], number[]][][])) =>{
                    let results = result.reduce((accumulator, value) => accumulator.concat(value), [])
                    let results_trans = results[0].map((_, colIndex) => results.map(row => row[colIndex]));
                    this.model.setv({
                        progress_percent: -1,
                        progress_status: 'Uploading data.  Please wait...'
                    })
                    this.model.setv({
                        transfered_text: results_trans.slice(0,4),
                        transfered_data: results_trans.slice(4),
                    })
                    this.model.setv({
                        progress_state: 2,
                        progress_percent: 0,
                        progress_status: 'Transfer complete, storing data...'
                    })
                })
            } else {
                throw new Error("bk_target_table is null")
            }
        } else {
            throw new Error("document is null")
        }
    }    
}

export namespace FileProgressInput {
  export type Attrs = p.AttrsOf<Props>

  export type Props = InputWidget.Props & {
    multiple: p.Property<boolean>,
    progress_state: p.Property<number>,
    progress_percent: p.Property<number>,
    progress_status: p.Property<string>,
    //file_params: p.Property<string[]>,
    file_type: p.Property<string>,
    //file_wavelengths: p.Property<{ [key: string]: number[] }>,
    harvest: p.Property<boolean>,
    transfered_text: p.Property<string[][]>,
    transfered_data: p.Property<number[][][]>
  }
}

export interface FileProgressInput extends FileProgressInput.Attrs {}

export class FileProgressInput extends InputWidget {
  declare properties: FileProgressInput.Props
  declare __view_type__: FileProgressInputView

  constructor(attrs?: Partial<FileProgressInput.Attrs>) {
    super(attrs)
  }

  static {
    this.prototype.default_view = FileProgressInputView
    this.define<FileProgressInput.Props>(({Number, String, Boolean, Array, Tuple}) => ({
        multiple:         [ Boolean, false ],
        progress_state:   [ Number, 0],
        progress_percent: [ Number, 0],
        progress_status:  [ String, "" ],
        //file_params:      [ Array(String), [""] ],
        file_type:        [ String, "" ],
        //file_wavelengths: [ Dict(Array(Number)), {} ],
        harvest:          [ Boolean, false ],
        transfered_text:  [ Array(Tuple(String)), [[""]]],
        transfered_data:  [ Array(Array(Tuple(Number))), [[[0]]] ]
    }))
  }
}
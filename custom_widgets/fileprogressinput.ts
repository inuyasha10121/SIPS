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

interface AB1File extends File{
    sample_name: string
    results: [number[], number[], number[], number[], number[], number[], number[], number[]]
}

class WorkerPool {
    max_workers: number
    worker_pool: Worker[]
    context: FileProgressInputView
    num_tasks: number

    constructor(context: FileProgressInputView){
        this.max_workers = Math.max(navigator.hardwareConcurrency, 4);
        this.worker_pool = [];
        this.context = context;
        this.num_tasks = 0;
    }
    _init_pool(worker_func: Function): void {
        const func_str = worker_func.toString();
        const funcBody = func_str.substring( func_str.indexOf( '{' ) + 1, func_str.lastIndexOf( '}' ) );
        const workerSourceURL = URL.createObjectURL( new Blob( [ funcBody ] ) );
        const num_workers = Math.min(this.num_tasks, this.max_workers)
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
                //TODO: Eventually, it might be better to display progress on each file, instead of each worker, resolve
                this.context.current_progress += 1 / this.worker_pool.length
                this.context.model.setv({
                    progress_percent: Math.round(100 * this.context.current_progress)
                })
                resolve(event.data)
            })
            worker.addEventListener('error', (event) => {
                reject(event.error)
            })
            worker.postMessage(input_data)
        })
    }
    async task_pool(worker_func: Function, task_arr: Array<any>, additional_data: any[]|null = null): Promise<any[]> {
        this.num_tasks = task_arr.length
        this.context.current_progress = 0
        this._init_pool(worker_func)
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
            this.model.setv({
                progress_status: "Reading data, this may take a while...",
            });
            this.harvest_data();
        });
    }

    override render(): void {
        super.render()
        
        const self = this
        if (this.worker_pool == null){
            this.worker_pool = new WorkerPool(self)
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
                    this.current_progress += 1 / (this.num_files * 2)
                    this.model.setv({
                        progress_percent: Math.round(100 * this.current_progress)
                    })
                    resolve([file, result as string])
                } else {
                    reject(reader.error ?? new Error(`unable to read '${file.name}'`))
                }
            }
            reader.onerror = () => {
                reject(new Error(`Error reading '${file.name}'`))
            }
            reader.readAsText(file);
        })
    }

    _read_parse_ABI(file: AB1File): Promise<AB1File> {
        return new Promise<AB1File>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => {
                const {result} = reader
                if (result != null) {
                    file.results = [[], [], [], [], [], [], [], []]
                    //Extract relevant entries from AB1 file
                    //https://projects.nfstc.org/workshops/resources/articles/ABIF_File_Format.pdf
                    var buffer = reader.result as ArrayBuffer
                    var view = new DataView(buffer);
                    var data_offset = view.getUint32(26);
                    var peak_inds: number[] = [];
                    for(var i = data_offset; i < view.byteLength; i += 28){
                        var name_tag = String.fromCharCode(view.getUint8(i)) + String.fromCharCode(view.getUint8(i+1)) + String.fromCharCode(view.getUint8(i+2)) + String.fromCharCode(view.getUint8(i+3)) + view.getUint32(i+4);
                        if(name_tag == "SMPL1"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            var smpl_arr = new Uint8Array(buffer, offset+1, count-1);
                            file.sample_name = new TextDecoder().decode(smpl_arr);
                        } else if (name_tag == "PLOC1"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            var peak_inds = Array<number>(count);
                            for(var j = 0; j < count; j++){
                                peak_inds[j] = view.getUint16(offset + (2*j));
                            }
                        } else if (name_tag == "DATA9"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            file.results[0] = Array(count);
                            for(var j = 0; j < count; j++){
                                file.results[0][j] = view.getUint16(offset + (2*j));
                            }
                        } else if (name_tag == "DATA10"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            file.results[1] = Array(count);
                            for(var j = 0; j < count; j++){
                                file.results[1][j] = view.getUint16(offset + (2*j));
                            }
                        } else if (name_tag == "DATA11"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            file.results[2] = Array(count);
                            for(var j = 0; j < count; j++){
                                file.results[2][j] = view.getUint16(offset + (2*j));
                            }
                        } else if (name_tag == "DATA12"){
                            var count = view.getUint32(i+12);
                            var offset = view.getUint32(i+20);
                            file.results[3] = Array(count);
                            for(var j = 0; j < count; j++){
                                file.results[3][j] = view.getUint16(offset + (2*j));
                            }
                        }
                    }
                    //Reduce down data to only key points of interest
                    var midpoints = [...Array(peak_inds.length - 1).keys()].map(i => Math.floor((peak_inds[i+1] - peak_inds[i]) / 2) + peak_inds[i]);
                    file.results[4] = midpoints.map(i => file.results[0][i]); //DATA9
                    file.results[5] = midpoints.map(i => file.results[1][i]); //DATA10
                    file.results[6] = midpoints.map(i => file.results[2][i]); //DATA11
                    file.results[7] = midpoints.map(i => file.results[3][i]); //DATA12
                    file.results[0] = peak_inds.map(i => file.results[0][i]); //DATA9
                    file.results[1] = peak_inds.map(i => file.results[1][i]); //DATA10
                    file.results[2] = peak_inds.map(i => file.results[2][i]); //DATA11
                    file.results[3] = peak_inds.map(i => file.results[3][i]); //DATA12
                    //Pad to make all lines equal in length
                    file.results[4].push(0)
                    file.results[5].push(0)
                    file.results[6].push(0)
                    file.results[7].push(0)
                    this.current_progress += 1 / this.num_files
                    this.model.setv({
                        progress_percent: Math.round(100 * this.current_progress)
                    })
                    resolve(file)
                } else {
                    reject(reader.error ?? new Error(`unable to read '${file.name}'`))
                }
            }
            reader.onerror = () => {
                reject(new Error(`Error reading '${file.name}'`))
            }
            reader.readAsArrayBuffer(file);
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
                const self = this;
                function _extract_empower_params(file: EmpowerFile, content: string): Promise<EmpowerFile>{
                    return new Promise<EmpowerFile>((resolve, reject) => {
                        if (content != null){
                            function progress_resolve(file: EmpowerFile): void{
                                self.current_progress += 1 / (self.num_files * 2)
                                self.model.setv({
                                    progress_percent: Math.round(100 * self.current_progress)
                                })
                                resolve(file)
                            }
                            //First, check to see if we have the necessary information in the header
                            let content_lines = content.split(/[\x0D\x0a]+/g)
                            const header_labels = content_lines[0].split(/\t/g)
                            const header_content = content_lines[1].split(/\t/g)
            
                            const channel_ind = header_labels.indexOf("\"Channel Description\"")
                            if (channel_ind == -1){
                                console.log(header_labels)
                                reject(new Error(`${file.name} is missing a channel description`))
                            }
                            const channel_desc = header_content[channel_ind]
            
                            const vial_ind = header_labels.indexOf("\"Vial\"")
                            if (vial_ind == -1){
                                reject(new Error(`${file.name} is missing a vial ID`))
                            }
                            let vial_bits = ["",""]
                            try{
                                vial_bits = header_content[vial_ind].replace(/\"/g, "").split(':')[1].split(',')
                            } catch (error) {
                                console.log(file.name)
                                console.log("0> " + header_content[vial_ind])
                                console.log("1> " + header_content[vial_ind].replace(/\"/g, ""))
                                console.log("2> " + header_content[vial_ind].replace(/\"/g, "").split(':'))
                                console.log("3> " + header_content[vial_ind].replace(/\"/g, "").split(':')[1])
                                console.log("4> " + header_content[vial_ind].replace(/\"/g, "").split(':')[1].split(','))
                                throw error
                            }
                            //let vial_bits = header_content[vial_ind].slice(2).split(',')
                            vial_bits[1] = vial_bits[1].padStart(2, '0')
                            file.well = vial_bits[0].toUpperCase() + vial_bits[1]
            
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
                                    file.wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
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
                                    file.wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
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
                break;
            case 'fasta':
                this.model.setv({
                    progress_state: 0,
                    progress_percent: 0,
                    progress_status: 'Preprocessing data...',
                })
                //This is alignment data from a sequencing run, to be used in AReS
                Promise.all(Array.from(files).map(async (file) => {
                    return await this._read_file_text(file)
                })).then((read_files) => {
                    let content_lines = read_files[0][1].split(/[\x0D\x0a]+/g)
                    let counter = -1;
                    let entries: string[][] = [];
                    for(let i = 0; i < content_lines.length; i++){
                        if (content_lines[i].startsWith('>')){
                            entries.push([content_lines[i].slice(1), ""])
                            counter += 1;
                        } else {
                            entries[counter][1] += content_lines[i]
                        }
                    }

                    this.model.setv({
                        file_type: 'FASTA',
                        progress_state: 1,
                        progress_percent: -1,
                        progress_status: 'Parameters extracted!  Please input harvesting info.',
                        transfered_text: entries
                    })
                })
                break;
            case 'ab1':
                this.model.setv({
                    progress_state: 0,
                    progress_percent: 0,
                    progress_status: 'Preprocessing data...',
                })
                //This is fluoresences data from a sequencing read, to be used in AReS
                Promise.all(Array.from(files).map(async (file) => {
                    return await this._read_parse_ABI(file as AB1File)
                })).then((results) => {
                    this.model.setv({
                        file_type: 'AB1',
                        progress_state: 1,
                        progress_percent: -1,
                        progress_status: 'Parameters extracted!  Please input harvesting info.',
                        transfered_text: [results.map(function(value) { return value.sample_name })]
                    })
                })
                
                break;
            case 'bin':
                //This is an archival file from the software 
                break;
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
        const ext = (<FileList>this.input_el.files)[0].name.split('.').pop()
        switch(ext){
            case 'arw':
                //Extract out everything the user specified from the data selection table
                if (this.model.document != null){
                    let dst_model = this.model.document.get_model_by_name('bk_fi_target_table')
                    if (dst_model != null){
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
                        console.log("TABLE PARAMS")
                        console.log(harvest_compounds)
                        console.log(harvest_sources)
                        console.log(harvest_targets)
                        //Now, we can read the files
                        this.model.setv({
                            progress_percent: 0,
                            progress_status: 'Harvesting requested data...'
                        })

                        //function harvest_empower_data(){
                        //    async function _read_file_text(file: File): Promise<string> {
                        //        return new Promise<string>((resolve, reject) => {
                        //            const reader = new FileReader()
                        //            reader.onload = () => {
                        //                const {result} = reader
                        //                if (result != null) {
                        //                    resolve(result as string)
                        //                } else {
                        //                    reject(reader.error ?? new Error(`unable to read '${file.name}'`))
                        //                }
                        //            }
                        //            reader.onerror = () => {
                        //                reject(new Error(`Error reading '${file.name}'`));
                        //            }
                        //            reader.readAsText(file);
                        //        })
                        //    }
                        //    
                        //    async function _harvest_empower_file(content: string, harvest_compounds: string[], harvest_sources: string[], harvest_targets: number[]): Promise<[string, string, string, string, number[], number[]][]> {
                        //        return new Promise((resolve) => {
                        //            //const self = this
                        //            function progress_resolve(parsed_data: [string, string, string, string, number[], number[]][]): void{
                        //                console.log("PARSED DATA")
                        //                parsed_data.forEach(function (row) {
                        //                    console.log(`${row[0]}\t${row[1]}\t${row[2]}\t${row[3]}\t${row[4].length}\t${row[5].length}`)
                        //                })
                        //                resolve(parsed_data)
                        //            }
                        //
                        //            function parse_data(array: string[]): number[][] {
                        //                let values = array.map(line => {
                        //                    return line.split(/\s+/g).map(num => {
                        //                      return parseFloat(num)
                        //                  })
                        //                })
                        //                return values.map((_, colIndex) => values.map(row => row[colIndex]));
                        //            }
                        //            
                        //            //Re-extract our relevant parameters from the header
                        //            //First, check to see if we have the necessary information in the header
                        //            let content_lines = content.split(/[\x0D\x0a]+/g)
                        //            const header_labels = content_lines[0].split(/\t/g)
                        //            const header_content = content_lines[1].split(/\t/g)
                        //            
                        //            const vial_ind = header_labels.indexOf("\"Vial\"")
                        //            let vial_bits = header_content[vial_ind].slice(3, -1).split(',')
                        //            vial_bits[1] = vial_bits[1].padStart(2, '0')
                        //            const well = vial_bits[0].toUpperCase() + vial_bits[1]
                        //            
                        //            let sample_name = ""
                        //            const sample_ind = header_labels.indexOf("\"SampleName\"")
                        //            if (sample_ind != -1) {
                        //                sample_name = header_content[sample_ind].slice(1, -1)
                        //            }
                        //            
                        //            const channel_ind = header_labels.indexOf("\"Channel Description\"")
                        //            const channel_desc = header_content[channel_ind]
                        //
                        //            let tag = ""
                        //            let wavelengths: number[] = []
                        //            if (channel_desc.includes('QDa')){
                        //                if (channel_desc.includes('Scan')) {
                        //                    wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
                        //                    if (channel_desc.includes('Positive')){
                        //                        tag = '(+)MS Scan'
                        //                    } else if (channel_desc.includes('Negative')){
                        //                        tag = '(-)MS Scan'
                        //                    }
                        //                } else if (channel_desc.includes('SIR')){
                        //                    const desc_split = channel_desc.split(/[ ,]+/g)
                        //                    const sir_mz = desc_split[desc_split.indexOf('Da')-1]
                        //                    if (channel_desc.includes('Positive')){
                        //                        tag = `(+)SIR ${sir_mz} m/z`
                        //                    } else if (channel_desc.includes('Negative')){
                        //                        tag = `(-)SIR ${sir_mz} m/z`
                        //                    }
                        //                }
                        //            } else if (channel_desc.includes('PDA')) {
                        //                if (channel_desc.includes('Spectrum')) {
                        //                    wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
                        //                    tag = `PDA Scan`
                        //                } else if (channel_desc.includes('@')) {
                        //                    const desc_split = channel_desc.split(/[ ,]+/g)
                        //                    const wl_ind = desc_split.findIndex(el => el.includes('@'))
                        //                    const wl = desc_split[wl_ind].split('@')[0]
                        //                    tag = wl
                        //                }
                        //            }
                        //            
                        //
                        //            //Go through all our harvested sources
                        //            let results: [string, string, string, string, number[], number[]][] = []
                        //            for (let i = 0; i < harvest_sources.length; i++){
                        //                //Check if the file source matches
                        //                if (harvest_sources[i] == tag){
                        //                    let compound = harvest_compounds[i]
                        //                    //Check for 3D or 2D data
                        //                    if (wavelengths.length > 0){
                        //                        let parsed_content = parse_data(content_lines.slice(4, -1))
                        //                        let target = harvest_targets[i]
                        //                        //Make our tag more descriptive
                        //                        let new_tag = ""
                        //                        if (tag.includes('MS')){
                        //                            new_tag = `${tag.substring(0, 3)}XIC ${target} m/z`
                        //                        } else {
                        //                            new_tag = `XAC ${target} nm`
                        //                        }
                        //                        //Find the closest wavelength or m/z to the target
                        //                        function find_closest(arr: number[], target: number): number{
                        //                            let diff = Math.abs(arr[0] - target)
                        //                            let best = 0
                        //                            for (let i = 1; i < arr.length; i++){
                        //                                if (Math.abs(arr[i] - target) < diff){
                        //                                    best = i
                        //                                }
                        //                            }
                        //                            return best
                        //                        }
                        //                        let closest_wl_ind = find_closest(wavelengths, target)
                        //                        results.push([sample_name, well, compound, new_tag, parsed_content[0], parsed_content[closest_wl_ind]])
                        //                    } else {
                        //                        let parsed_content = parse_data(content_lines.slice(2, -1))
                        //                        //Easy push
                        //                        results.push([sample_name, well, compound, tag, parsed_content[0], parsed_content[1]])
                        //                    }
                        //                }
                        //            }
                        //            progress_resolve(results)
                        //        });
                        //    }
                        //    
                        //    self.addEventListener('message', async (event) => {
                        //        const files: EmpowerFile[] = event.data.slice(0,-3)
                        //        const harvest_compounds: string[] = event.data[event.data.length-3]
                        //        const harvest_sources: string[] = event.data[event.data.length-2]
                        //        const harvest_targets: number[] = event.data[event.data.length-1]
                        //        Promise.all(
                        //            files.map(async (file: EmpowerFile) => {
                        //                const content = await _read_file_text(file)
                        //                const parsed_content = await _harvest_empower_file(content, harvest_compounds, harvest_sources, harvest_targets)
                        //                return parsed_content
                        //            })
                        //        ).then((extractedValues: [string, string, string, string, number[], number[]][][]) => {
                        //            self.postMessage(extractedValues)
                        //        })
                        //    })
                        //}
                        //console.log(this.input_el.files)
                        //this.worker_pool.task_pool(harvest_empower_data, Array.from(this.input_el.files as FileList), [harvest_compounds, harvest_sources, harvest_targets]).then((result: ([string, string, string, string, number[], number[]][][])) =>{
                        //    let results = result.reduce((accumulator, value) => accumulator.concat(value), [])
                        //    console.log("RESULTS");
                        //    console.log(results);
                        //    let results_trans = results[0].map((_, colIndex) => results.map(row => row[colIndex]));
                        //    console.log("TRANSPOSED RESULTS");
                        //    console.log(results_trans);
                        //    this.model.setv({
                        //        progress_percent: -1,
                        //        progress_status: 'Uploading data.  Please wait...'
                        //    })
                        //    this.model.setv({
                        //        transfered_text: results_trans.slice(0,4),
                        //        transfered_data: results_trans.slice(4),
                        //    })
                        //    this.model.setv({
                        //        progress_state: 2,
                        //        progress_percent: 0,
                        //        progress_status: 'Transfer complete!'
                        //    })
                        //})
                        
                        this.current_progress = 0
                        Promise.all(Array.from(this.input_el.files as FileList).map(async (file) => {
                            async function _read_file_text(file: File): Promise<string> {
                                console.log(`Reading ${file.name}...`)
                                return new Promise<string>((resolve, reject) => {
                                    const reader = new FileReader()
                                    reader.onload = () => {
                                        const {result} = reader
                                        if (result != null) {
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
                                        resolve(parsed_data)
                                    }

                                    function parse_data(array: string[]): number[][] {
                                        let values = array.map(line => {
                                            return line.split(/\s+/g).map(num => {
                                              return parseFloat(num)
                                          })
                                        })
                                        return values.map((_, colIndex) => values.map(row => row[colIndex]));
                                    }

                                    //Re-extract our relevant parameters from the header
                                    //First, check to see if we have the necessary information in the header
                                    console.log("Extracting header information")
                                    let content_lines = content.split(/[\x0D\x0a]+/g)
                                    const header_labels = content_lines[0].split(/\t/g)
                                    const header_content = content_lines[1].split(/\t/g)

                                    const vial_ind = header_labels.indexOf("\"Vial\"")
                                    //let vial_bits = header_content[vial_ind].slice(3, -1).split(',')
                                    let vial_bits = header_content[vial_ind].replace(/\"/g, "").split(':')[1].split(',')
                                    vial_bits[1] = vial_bits[1].padStart(2, '0')
                                    const well = vial_bits[0].toUpperCase() + vial_bits[1]

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
                                            wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
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
                                            wavelengths = content_lines[2].split(/\s+/g).slice(1).map(parseFloat);
                                            tag = `PDA Scan`
                                        } else if (channel_desc.includes('@')) {
                                            const desc_split = channel_desc.split(/[ ,]+/g)
                                            const wl_ind = desc_split.findIndex(el => el.includes('@'))
                                            const wl = desc_split[wl_ind].split('@')[0]
                                            tag = wl
                                        }
                                    }


                                    console.log("Extracting data")
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
                            const content = await _read_file_text(file)
                            const parsed_content = await _harvest_empower_file(content, harvest_compounds, harvest_sources, harvest_targets)

                            this.current_progress += 1 / this.num_files
                            this.model.setv({
                                progress_percent: Math.round(100 * this.current_progress)
                            })
                            return parsed_content
                        })).then((result: ([string, string, string, string, number[], number[]][][])) =>{
                            console.log("Reshaping data")
                            console.log(result)
                            let results = result.reduce((accumulator, value) => accumulator.concat(value), [])
                            let results_trans = results[0].map((_, colIndex) => results.map(row => row[colIndex]));
                            this.model.setv({
                                progress_percent: -1,
                                progress_status: 'Uploading data.  Please wait...'
                            })
                            console.log("Uploading data")
                            this.model.setv({
                                transfered_text: results_trans.slice(0,4),
                                transfered_data: results_trans.slice(4),
                            })
                            this.model.setv({
                                progress_state: 2,
                                progress_percent: 0,
                                progress_status: 'Transfer complete!'
                            })
                        })
                    } else {
                        throw new Error("bk_target_table is null")
                    }
                } else {
                    throw new Error("document is null")
                }
                break;
            case "fasta":
                this.model.setv({
                    progress_state: 2,
                    progress_percent: 0,
                    progress_status: 'Transfer complete!'
                })
                break;
            case "ab1":
                this.model.setv({
                    progress_percent: -1,
                    progress_status: 'Uploading data.  Please wait...'
                })
                let sample_names: string[] = []
                let bin_data: number[][][] = []
                Array.from(this.input_el.files as FileList).forEach((file: File) => {
                    let ab1_file = (file as AB1File)
                    sample_names.push(ab1_file.sample_name)
                    bin_data.push(ab1_file.results)

                })
                this.model.setv({
                    transfered_text: [sample_names],
                    transfered_data: bin_data,
                })
                this.model.setv({
                    progress_state: 2,
                    progress_percent: 0,
                    progress_status: 'Transfer complete!'
                })
                break;
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
    file_type: p.Property<string>,
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
        file_type:        [ String, "" ],
        harvest:          [ Boolean, false ],
        transfered_text:  [ Array(Tuple(String)), [[""]]],
        transfered_data:  [ Array(Array(Tuple(Number))), [[[0]]] ]
    }))
  }
}
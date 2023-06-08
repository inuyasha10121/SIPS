function harvest_empower_params(){
    interface EmpowerFile extends File {
        tag: string
        sample_name: string
        well: string
        wavelengths: number[]
        content3d: boolean
    
    }
    
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
                    console.log("File read")
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
    
    async function _extract_empower_params(file: EmpowerFile, content: string): Promise<EmpowerFile>{
        return new Promise<EmpowerFile>((resolve, reject) => {
            if (content != null){
                //const self = this
                function progress_resolve(file: EmpowerFile): void{
                    //self.current_progress += 1 / (self.num_files * 2)
                    //self.model.setv({
                    //    progress_percent: Math.round(100 * self.current_progress)
                    //})
                    console.log('Params parsed')
                    resolve(file)
                }
                //First, check to see if we have the necessary information in the header
                let content_lines = content.split(/[\x0D\x0a]+/g)
                const header_labels = content_lines[0].split(/\t/)
                const header_content = content_lines[1].split(/\t/)
    
                const channel_ind = header_labels.indexOf("\"Channel Description\"")
                if (channel_ind == -1){
                    reject(new Error(`${file.name} is missing a channel description`))
                }
                const channel_desc = header_content[channel_ind]
    
                const vial_ind = header_labels.indexOf("\"Vial\"")
                if (vial_ind == -1){
                    reject(new Error(`${file.name} is missing a vial ID`))
                }
                let vial_bits = header_content[vial_ind].slice(3, -1).split(',')
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
                        file.wavelengths = content_lines[2].split(/\t/).slice(1).map(parseFloat);
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
                        const desc_split = channel_desc.split(/[ ,]+/)
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
                        file.wavelengths = content_lines[2].split(/\t/).slice(1).map(parseFloat);
                        file.content3d = false
                        file.tag = `PDA Scan`
                        progress_resolve(file)
                    } else if (channel_desc.includes('@')) {
                        file.content3d = false
                        file.wavelengths = []
                        const desc_split = channel_desc.split(/[ ,]+/)
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
    
    self.addEventListener('message', async (event) => {
        const files: File[] = event.data;
        Promise.all(
            files.map(async (file: File) => {
                const content = await _read_file_text(file)
                return await _extract_empower_params(file as EmpowerFile, content)
            })
        ).then((extractedValue: EmpowerFile[]) => {
            self.postMessage(extractedValue)
        })
    })
}
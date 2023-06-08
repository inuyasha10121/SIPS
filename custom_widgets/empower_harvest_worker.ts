function harvest_empower_data(){
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
    
    async function _harvest_empower_file(file: EmpowerFile, content: string, harvest_compounds: string[], harvest_sources: string[], harvest_targets: number[]): Promise<[string, string, string, string, number[], number[]][]> {
        return new Promise((resolve) => {
            //const self = this
            function progress_resolve(parsed_data: [string, string, string, string, number[], number[]][]): void{
                //self.current_progress += 1 / (self.num_files * 2)
                //self.model.setv({
                //    progress_percent: Math.round(100 * self.current_progress)
                //})
                console.log("Data harvested")
                resolve(parsed_data)
            }

            function parse_data(array: string[]): number[][] {
                let values = array.map(line => {
                    return line.split(/\t/).map(num => {
                      return parseFloat(num)
                  })
                })
                return values.map((_, colIndex) => values.map(row => row[colIndex]));
            }
            
            //Go through all our harvested sources
            let results: [string, string, string, string, number[], number[]][] = []
            for (let i = 0; i < harvest_sources.length; i++){
                //Check if the file source matches
                if (harvest_sources[i] == file.tag){
                    let compound = harvest_compounds[i]
                    //Check for 3D or 2D data
                    if (file.content3d){
                        let parsed_content = parse_data(content.split(/[\x0D\x0a]+/g).slice(4, -1))
                        let target = harvest_targets[i]
                        //Make our tag more descriptive
                        let new_tag = ""
                        if (file.tag.includes('MS')){
                            new_tag = `${file.tag.substring(0, 3)}XIC ${target} m/z`
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
                        let closest_wl_ind = find_closest(file.wavelengths, target)
                        results.push([file.sample_name, file.well, compound, new_tag, parsed_content[0], parsed_content[closest_wl_ind]])
                    } else {
                        let parsed_content = parse_data(content.split(/[\x0D\x0a]+/g).slice(2, -1))
                        //Easy push
                        results.push([file.sample_name, file.well, compound, file.tag, parsed_content[0], parsed_content[1]])
                    }
                }
            }
            progress_resolve(results)
        });
    }
    
    self.addEventListener('message', async (event) => {
        const {files, harvest_compounds, harvest_sources, harvest_targets} = event.data;
        Promise.all(
            files.map(async (file: File) => {
                const content = await _read_file_text(file)
                return await _harvest_empower_file(file as EmpowerFile, content, harvest_compounds, harvest_sources, harvest_targets)
            })
        ).then((extractedValue: [string, string, string, string, number[], number[]][][]) => {
            self.postMessage(extractedValue)
        })
    })
}
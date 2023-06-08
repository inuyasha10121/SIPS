// See https://docs.bokeh.org/en/latest/docs/reference/models/layouts.html
import * as p from "core/properties"
//import {div} from "core/dom"
import { InputWidget, InputWidgetView } from "models/widgets/input_widget"

// The view of the Bokeh extension/ HTML element
// Here you can define how to render the model as well as react to model changes or View events.
export class DataSelectionTableView extends InputWidgetView {
    declare model: DataSelectionTable
    table_el: HTMLTableElement

    compoundCells: Array<HTMLTableCellElement>
    sourceCells: Array<HTMLTableCellElement>
    targetCells: Array<HTMLTableCellElement>
    
    leftButtonElement: HTMLButtonElement
    rightButtonElement: HTMLButtonElement

    connect_signals(): void {
        super.connect_signals()

        this.connect(this.model.properties.update_sources.change, () => {
            this.change_options();
        });
    }

    override render(): void {
        super.render()

        if (this.compoundCells == null){
            this.compoundCells = [];
        }
        
        if (this.sourceCells == null){
            this.sourceCells = [];
        }
        
        if (this.targetCells == null){
            this.targetCells = [];
        }

        if (this.table_el == null) {
            //Setup table
            this.table_el = document.createElement('table');
            var header = this.table_el.createTHead();
            var row = header.insertRow(0);
            var cell = row.insertCell(0);
            cell.innerHTML = "<b>Compound:</b>";
            cell = row.insertCell(1);
            cell.innerHTML = "<b>Source:</b>";
            cell = row.insertCell(2);
            cell.innerHTML = "<b>Target:</b>";
            var body = this.table_el.createTBody();
            //Add all cells to table
            for(var i = 0; i < this.model.cells_per_page; i++){
                var row = body.insertRow(i);
                //Compound name cell
                var cell = row.insertCell(0);
                var cell_input = <HTMLInputElement>document.createElement('input');
                cell_input.id = "c_" + i;
                cell_input.onchange = (e) => {
                    var targ = (e.target as HTMLInputElement);
                    var cell_ind = parseInt(targ.id.substring(2));
                    //Store changed value
                    this.model.compounds[(this.model.curr_page * this.model.cells_per_page) + cell_ind] = targ.value;
                }
                cell.appendChild(cell_input);
                this.compoundCells.push(cell);
                
                //Data source cell
                var cell = row.insertCell(1);
                var sele_input = <HTMLSelectElement>document.createElement('select');
                sele_input.id = "s_" + i;
                sele_input.onchange = (e) => {
                    var targ = (e.target as HTMLSelectElement);
                    var cell_ind = parseInt(targ.id.substring(2));
                    var val = targ.value;
                    //Disable target input if source is 2D
                    (<HTMLInputElement>this.targetCells[cell_ind].children[0]).disabled = !this.model.possible_sources[this.model.possible_sources.indexOf(val)].includes('Scan');
                    (<HTMLInputElement>this.targetCells[cell_ind].children[0]).value = "";
                    //Store changed value
                    this.model.sources[(this.model.curr_page * this.model.cells_per_page) + cell_ind] = targ.value;
                };
                cell.appendChild(sele_input);
                this.sourceCells.push(cell);
                
                //Target specification cell
                var cell = row.insertCell(2);
                var cell_input = <HTMLInputElement>document.createElement('input');
                cell_input.id = "t_" + i;
                cell_input.type = "number";
                cell_input.onchange = (e) => {
                    //Snap the input value to the closest possible value
                    var targ = (e.target as HTMLInputElement);
                    var cell_ind = parseInt(targ.id.substring(2));
                    var source_val = (<HTMLSelectElement>this.sourceCells[cell_ind].children[0]).value;
                    var new_value = parseFloat(targ.value);
                    var closest = this.model.wavelengths_3d[source_val].reduce(function(prev: number, curr: number) {
                        return (Math.abs(curr - new_value) < Math.abs(prev - new_value) ? curr : prev);
                    });
                    targ.value = closest.toString();
                    //Store changed value
                    this.model.targets[(this.model.curr_page * this.model.cells_per_page) + cell_ind] = targ.value;
                }
                cell.appendChild(cell_input);
                this.targetCells.push(cell); //Save cell for later manipulation
            }

            if (this.leftButtonElement == null) {
                this.leftButtonElement = document.createElement('button');
                this.leftButtonElement.style.visibility = 'hidden';
                this.leftButtonElement.innerHTML = "\u25C0";
                this.leftButtonElement.onclick = () => {
                    this.model.curr_page -= 1;
                    this.check_buttons();
                }
            }
            
            if (this.rightButtonElement == null) {
                this.rightButtonElement = document.createElement('button');
                this.rightButtonElement.innerHTML = "\u25B6";
                this.rightButtonElement.onclick = () => {
                    this.model.curr_page += 1;
                    this.check_buttons();
                }
            }
            var buttonsContainer = document.createElement('div');
            buttonsContainer.style.display = 'flex';

            // Append the button elements to the buttonsContainer div
            buttonsContainer.appendChild(this.leftButtonElement);
            buttonsContainer.appendChild(this.rightButtonElement);

            // Append the buttonsContainer div and table element to this.group_el
            this.group_el.appendChild(this.table_el);
            this.group_el.appendChild(buttonsContainer);
        }
        
    }
    check_buttons(): void {
        //Make sure we are showing advance buttons one when needed
        if (this.model.curr_page == 0){
            this.leftButtonElement.style.visibility = 'hidden';
        } else {
            this.leftButtonElement.style.visibility = 'visible';
        }
        if (this.model.curr_page == (this.model.max_pages-1)){
            this.rightButtonElement.style.visibility = 'hidden';
        } else {
            this.rightButtonElement.style.visibility = 'visible';
        }
        this.refresh_table();
    }
    refresh_table(): void {
        for(var i = 0; i < this.model.cells_per_page; i++){
            (<HTMLInputElement>this.compoundCells[i].children[0]).value = this.model.compounds[(this.model.curr_page * this.model.cells_per_page) + i];
            (<HTMLSelectElement>this.sourceCells[i].children[0]).value = this.model.sources[(this.model.curr_page * this.model.cells_per_page) + i];
            
            if (this.model.possible_sources[this.model.possible_sources.indexOf(this.model.sources[(this.model.curr_page * this.model.cells_per_page) + i])].includes('Scan')) {
                (<HTMLInputElement>this.targetCells[i].children[0]).disabled = false;
                (<HTMLInputElement>this.targetCells[i].children[0]).value = this.model.targets[(this.model.curr_page * this.model.cells_per_page) + i];
            } else {
                (<HTMLInputElement>this.targetCells[i].children[0]).disabled = true;
                (<HTMLInputElement>this.targetCells[i].children[0]).value = "";
            }
        }
    }
    change_options(): void {
        //Save any reusable specifications
        var c = 0;

        for (var i = 0; i < this.model.compounds.length; i++){
            if((this.model.compounds[i] != "") && (this.model.possible_sources.includes(this.model.sources[i]))){
                console.log("ADDING")
                let compound = this.model.compounds[i];
                let source = this.model.sources[i];
                let target = this.model.targets[i];
                this.model.compounds[i] = "";
                this.model.sources[i] = this.model.possible_sources[0];
                this.model.targets[i] = "";
                this.model.compounds[c] = compound;
                this.model.sources[c] = source;
                this.model.targets[c] = target;
                c += 1;
            } else {
                this.model.compounds[i] = "";
                this.model.sources[i] = this.model.possible_sources[0];
                this.model.targets[i] = "";
            }
        }
        this.model.compounds = this.model.compounds;
        this.model.sources = this.model.sources;
        this.model.targets = this.model.targets;
        //Change options
        for (var i = 0; i < this.sourceCells.length; i++) {
            //Clear options
            this.sourceCells[i].children[0].innerHTML = "";
            //Add new options on
            this.model.possible_sources.forEach((option) => {
                var opt = document.createElement('option');
                opt.value = option;
                opt.innerHTML = option;
                this.sourceCells[i].children[0].appendChild(opt);
            });
        }
        this.refresh_table();
    }
}

export namespace DataSelectionTable {
    export type Attrs = p.AttrsOf<Props>
    export type Props = InputWidget.Props & {
        cells_per_page: p.Property<number>,
        max_pages: p.Property<number>,
        curr_page: p.Property<number>,
        compounds: p.Property<string[]>,
        sources: p.Property<string[]>,
        targets: p.Property<string[]>,
        possible_sources: p.Property<string[]>,
        wavelengths_3d: p.Property<{ [key: string]: number[] }>,
        update_sources: p.Property<boolean>,
    }
}

export interface DataSelectionTable extends DataSelectionTable.Attrs { }

export class DataSelectionTable extends InputWidget {
    declare properties: DataSelectionTable.Props
    declare __view_type__: DataSelectionTableView

    constructor(attrs?: Partial<DataSelectionTable.Attrs>) {
        super(attrs)
    }
    
    bepo(): void {
        console.log("bepo");
    }

    static {
        this.prototype.default_view = DataSelectionTableView;
        this.define<DataSelectionTable.Props>(({Number, Boolean, String, Array, Dict}) => ({
            cells_per_page:    [ Number, 10 ],
            max_pages:         [ Number, 3 ],
            curr_page:         [ Number, 0 ],
            compounds:         [ Array(String), [""] ],
            sources:           [ Array(String), [""] ],
            targets:           [ Array(String), [""] ],
            possible_sources:  [ Array(String), [""] ],
            wavelengths_3d:    [ Dict(Array(Number)), {} ],
            update_sources:    [ Boolean, false ],
        }))
    }
}
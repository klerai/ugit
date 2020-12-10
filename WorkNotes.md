# Work Notes:

* Last update:    2020-12-10


## Issues: 

#### ugit status

- at one points list all files within the working directory which have not 
been added to the object database, but adds them automatically without the 
add/commit cycle.


#### base.init()
    
- if called for a second time, it overwrites the existing ref/head/master, 
thus leads to python recursive function error when calling data.get_ref()
             
- **Solution:** Skip if 'refs/heads/master' already exists.


## General changes / enhancements

* For an interactive development and test cycles, respective cli-, base- and data-layer are implemented as Jupyter Notebooks (including an UGIT-test notebook)

* Module 'os' is replaced by 'pathlib', and 'argparse' with 'typer'
    
* Module 'typer' provides better data validation and help text to the user interface.
	- Check out:  **python3 cli.py** without sub commands
    
* as base.get_working_tree() and base.add() share the same file tree scanning mechanism, it was factored out into the new function: scan_dir()

* base.is_ignored() is expanded by additional files/directory exclusions
    
    


## Independent test routines:

```
#!/usr/bin/env python3
# list heads of all object files in .ugit/objects
#
from pathlib import Path

p = Path ('.ugit/objects')

for f in (fp for fp in p.rglob('*') if fp.is_file()):
     print(f.name, '\t', f.read_bytes()[0:20])
```


## INFO:

### UGIT Data Structure:

    .ugit/index
        - json file

    .ugit/objects/{OIDs} 
        - data object files with {Object IDs as file name}
        - with types like such as'{blob', 'commit' or 'tree'
          Format: {type} b{00} data

    .ugit/HEAD
        - points to the head of the current working tree
          Format: ref: filepath

    .ugit/refs/heads/master
              /remote/master
        - pointer to the head object by its OID     
          Format:     filepath, OID
    .ugit/refs/tags
        - pointer to specied commit OID
        Format:     OID
    .ugit/refs/branch
        - pointer to specied branch OID
        Format:     OID


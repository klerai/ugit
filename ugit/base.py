# File: base.py
# Date: 2020-11-30

import itertools
import operator
import string

from pathlib import Path
from collections import deque, namedtuple

from ugit import data
from ugit import diff


def init ():
    data.init ()
    ref = 'refs/heads/master'
    # treat init() as a singleton event, or we mess up the reference tree
    if (data.GIT_DIR / ref).is_file():
        return 
    data.update_ref ('HEAD', data.RefValue (symbolic=True, value=ref))


def write_tree ():
    """ """
    # Index is flat, we need it as a tree of dictionaries
    index_as_tree = {}
    with data.get_index () as index:
        for path, oid in index.items ():
            path = path.split ('/')
            dirpath, filename = path[:-1], path[-1]
            
            current = index_as_tree
            # Find the dict for the directory of this file
            for dirname in dirpath:
                current = current.setdefault (dirname, {})
            current[filename] = oid
            
    def write_tree_recursive (tree_dict):
        entries = []
        for name, value in tree_dict.items ():
            if type (value) is dict:
                type_ = 'tree'
                oid = write_tree_recursive (value)
            else:
                type_ = 'blob'
                oid = value
            entries.append ((name, oid, type_))
            
        tree = ''.join (f'{type_} {oid} {name}\n'
                        for name, oid, type_
                        in sorted (entries))
        return data.hash_object (tree.encode (), 'tree')
    
    return write_tree_recursive (index_as_tree)


def _iter_tree_entries (oid):
    """Using a generator to fetch the tree file by OID
    and for each line in the file we return: type_, oid, filepath
    """
    if not oid:
        return ''
    return (entry.split (' ', 2) 
            for entry in data.get_object (oid, 'tree').decode ().splitlines ())


def get_tree (oid, base_path=''):
    result = {}
    for type_, oid, name in _iter_tree_entries (oid):
        assert '/' not in name
        # assert name not in ('..', '.')
        path = base_path + name
        if type_ == 'blob':
            result[path] = oid
        elif type_ == 'tree':
            result.update (get_tree (oid, f'{path}/'))
        else:
            assert False, f'Unknown tree entry {type_}'
    return result


def scan_dir(file_path):
    """ Scan directory tree for all valid files, and return
    a dictionary with file_paths and OIDs  """
    result = {}
    for fp in (fp for fp in file_path.rglob('*') 
               if not is_ignored(fp) and fp.is_file()):
        result [str(fp)] = data.hash_object(fp.read_bytes())
    return result    
    

def get_working_tree ():
    file_path = Path('.')
    return scan_dir(file_path)
    

def get_index_tree ():
    with data.get_index () as index:
        return index


def _empty_current_directory ():
    """ Remove all files/directories of the current tree (unless is_ignored)"""
    paths = []
    
    # First removing all files...
    for path in (fp for fp in Path('.').rglob ('*')
               if not is_ignored (fp)):
        if path.is_file ():
            path.unlink ()
        else:
            paths.append(path)
            
    # then removing all directories...
    paths.sort (reverse=True)
    for path in paths:
        path.rmdir()


def _checkout_index (index):
    """For every entry in the index, the respected object is copied to the given
    file path. Any missing directory structure is created during the process.
    """
    _empty_current_directory ()
    for path, oid in index.items ():
        fp = Path(path)
        if not fp.parent.is_dir():
            fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data.get_object (oid, 'blob'))
        

def read_tree (tree_oid, update_working=False):
    """ Read tree object from the database to the index file, 
    and checkout the files into the working directory.
    """
    with data.get_index () as index:
        index.clear ()
        index.update (get_tree (tree_oid))
        
        if update_working:
            _checkout_index (index)


def read_tree_merged (t_base, t_HEAD, t_other, update_working=False):
    with data.get_index () as index:
        index.clear ()
        index.update (diff.merge_trees (
            get_tree (t_base),
            get_tree (t_HEAD),
            get_tree (t_other)
        ))
        
        if update_working:
            _checkout_index (index)


def commit (message):
    """ Save commit object to the database 
    and adjust HEAD and references accordingly
    """
    # Record hash of last commit to HEAD
    commit = f'tree {write_tree ()}\n'

    HEAD = data.get_ref ('HEAD').value
    if HEAD:
        commit += f'parent {HEAD}\n'
    MERGE_HEAD = data.get_ref ('MERGE_HEAD').value
    if MERGE_HEAD:
        commit += f'parent {MERGE_HEAD}\n'
        data.delete_ref ('MERGE_HEAD', deref=False)
        
    commit += '\n'
    commit += f'{message}\n'

    oid = data.hash_object (commit.encode (), 'commit')
    
    data.update_ref ('HEAD', data.RefValue (symbolic=False, value=oid))
        
    return oid


def checkout (name):
    """ Reset the working directory to the given TAG/BRANCH/OID 
    and move the HEAD to this OID
    """
    # Read tree and move HEAD
    oid = get_oid (name)
    commit = get_commit (oid)
    read_tree (commit.tree, update_working=True)
    
    if is_branch (name):
        HEAD = data.RefValue (symbolic=True, value=f'refs/heads/{name}')
    else:
        HEAD = data.RefValue (symbolic=False, value=oid)
    
    data.update_ref ('HEAD', HEAD, deref=False)


def reset (oid):
    """ Resetting the HEAD to a given OID, is like undo all newer commits """
    data.update_ref ('HEAD', data.RefValue (symbolic=False, value=oid))
    

def merge (other):
    # Merge heads together
    HEAD = data.get_ref ('HEAD').value
    assert HEAD
    merge_base = get_merge_base (other, HEAD)
    c_other = get_commit (other)

    # Handle fast-forward merge
    if merge_base == HEAD:
        read_tree (c_other.tree, update_working=True)
        data.update_ref ('HEAD',
                         data.RefValue (symbolic=False, value=other))
        print ('Fast-forward merge, no need to commit')
        return
    
    data.update_ref ('MERGE_HEAD', data.RefValue (symbolic=False, value=other))
    
    c_base = get_commit (merge_base)
    c_HEAD = get_commit (HEAD)
    read_tree_merged (c_base.tree, c_HEAD.tree, c_other.tree, update_working=True)
    print ('Merged in working tree\nPlease commit')


def get_merge_base (oid1, oid2):
    parents1 = list (iter_commits_and_parents ({oid1}))
    
    for oid in iter_commits_and_parents ({oid2}):
        if oid in parents1:
            return oid
        
        
def is_ancestor_of (commit, maybe_ancestor):
    return maybe_ancestor in iter_commits_and_parents ({commit})


def create_tag (name, oid):
    """ Creating a tag object pointing to the given OID """
    data.update_ref (f'refs/tags/{name}', data.RefValue (symbolic=False, value=oid))


def create_branch (name, oid):
    """ Creating a branch object pointing to the given OID """
    data.update_ref (f'refs/heads/{name}', data.RefValue (symbolic=False, value=oid))


def iter_branch_names ():
    """ Return a generator yielding all branch names """
    return (ref[0].split('/')[-1] for ref in data.iter_refs ('refs/heads/'))
        

def is_branch (branch):
    return data.get_ref (f'refs/heads/{branch}').value is not None


def get_branch_name ():
    HEAD = data.get_ref ('HEAD', deref=False)
    if not HEAD.symbolic:
        return None
    HEAD = HEAD.value
    assert HEAD.startswith ('refs/heads/')
    return HEAD.split('/')[-1]


Commit = namedtuple ('Commit', ['tree', 'parents', 'message'])
Commit.__doc__ = """A name tuple representing a commit value
- with three fields:
  tree     - Object Id
  parents  - Object Id
  message  - associated text
"""

def get_commit (oid):
    parents = []
    
    commit = data.get_object (oid, 'commit').decode ()
    lines = iter (commit.splitlines ())
    for line in itertools.takewhile (operator.truth, lines):
        key, value = line.split (' ', 1)
        if key == 'tree':
            tree = value
        elif key == 'parent':
            parents.append (value)
        else:
            assert False, f'Unknown field {key}'
    
    message = '\n'.join (lines)
    return Commit (tree=tree, parents=parents, message=message)


def iter_commits_and_parents (oids):
    # N.B. Must yield the oid before accessing it.
    #      To allow caller to fetch it if needed)
    oids = deque (set (oids))
    visited = set ()
    
    while oids:
        oid = oids.popleft ()
        if not oid or oid in visited:
            continue
        visited.add (oid)
        yield oid
        
        commit = get_commit (oid)
        # Return first parent next
        oids.extendleft (commit.parents[:1])
        # Return other parents later
        oids.extend (commit.parents[1:])
    

def iter_objects_in_commits (oids):
    # N.B. Must yield the oid before accessing it.
    #      To allow caller to fetch it if needed)
    visited = set ()

    def iter_objects_in_tree (oid):
        visited.add (oid)
        yield oid
        for type_, oid, _ in _iter_tree_entries (oid):
            if oid not in visited:
                if type_ == 'tree':
                    yield from iter_objects_in_tree (oid)
                else:
                    visited.add (oid)
                    yield oid
                    
    for oid in iter_commits_and_parents (oids):
        yield oid
        commit = get_commit (oid)
        if commit.tree not in visited:
            yield from iter_objects_in_tree (commit.tree)


def get_oid (name):
    if name == '@': name = 'HEAD'
    
    # Name is ref
    refs_to_try = [
        f'{name}',
        f'refs/{name}',
        f'refs/tags/{name}',
        f'refs/heads/{name}',
    ]
    for ref in refs_to_try:
        if data.get_ref (ref, deref=False).value:
            return data.get_ref (ref).value

    # Name is SHA1
    is_hex = all (c in string.hexdigits for c in name)
    if len (name) == 40 and is_hex:
        return name

    assert False, f'Unknown name {name}'

          
def add (filenames):
    """ 
    Add one or more files/directories to the Index file
    Expects a list of file paths
    """
    with data.get_index () as index:
        for file_path in filenames:
            if is_ignored(file_path):
                continue
            elif file_path.is_file():
                # add file/hash for specified file
                index[str(file_path)] = data.hash_object(file_path.read_bytes())
            elif file_path.is_dir():
                # Add dictionary of files/hashes within specified path
                index.update(**scan_dir(file_path))    


def is_ignored (path):
    """ Filter criteria of files/dirs to be ignored """
    # exlude Python cache files
    if '__pycache__' in path.parts:        
        return False
    
    # notebook files to exclude
    if path.suffix == '.ipynb':
        return True
    
    # dirs to exclude
    for s in ['.ipynb_checkpoints', '.gitignore', '.ugit', 'ugit.egg-info']:
        if s in path.parts:
            return True
    
    return False                

    # orig: return '.ugit' in path.parts


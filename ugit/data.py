# File: data.py
# Date: 2020-11-29

import hashlib
import json

from pathlib import Path
from collections import namedtuple
from contextlib import contextmanager


GIT_DIR = Path('.ugit')

RefValue = namedtuple ('RefValue', ['symbolic', 'value'])
RefValue.__doc__ = """A named tuple representing a Reference Value
- with two fields:
  symbolic  - Boolean 
  value     - reference path
"""


@contextmanager
def change_git_dir (new_dir):
    """ Switches temporarily to a different .ugit directory, 
    yields control back to the caller, 
    and afterwards switches back to the previous .ugit directory
    """
    global GIT_DIR
    old_dir = GIT_DIR
    GIT_DIR = Path(new_dir) / '.ugit'
    yield
    GIT_DIR = old_dir


def init ():
    """ Initialize ugit's initial directory structure """
    (GIT_DIR / 'objects').mkdir(parents=True, exist_ok=True)


def update_ref (ref, value, deref=True):
    """ Update references such as Tags, Heads and Branches """
    ref = _get_ref_internal (ref, deref)[0]
    
    assert value.value
    if value.symbolic:
        value = f'ref: {value.value}'
    else:
        value = value.value
    
    # write value to the reference file,
    # while creating the correct file path, if needed
    ref_path = GIT_DIR / ref
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(value)

    
def get_ref (ref, deref=True):
    """ return reference or object Id """
    return _get_ref_internal (ref, deref)[1]


def delete_ref (ref, deref=True):
    """ Delete given reference """
    ref = _get_ref_internal (ref, deref)[0]
    (GIT_DIR / ref).unlink()


def _get_ref_internal (ref, deref):
    """ recursively scan through references """
    value = None
    ref_path = GIT_DIR / ref
    if ref_path.is_file():
        value = ref_path.read_text().strip()

    symbolic = bool (value) and value.startswith ('ref:')
    if symbolic:
        value = value.split (':', 1)[1].strip ()
        if deref:
            return _get_ref_internal (value, deref=True)

    return ref, RefValue (symbolic=symbolic, value=value)


def iter_refs (prefix='', deref=True):
    """ Iterator to return list of references """
    refs = ['HEAD', 'MERGE_HEAD']

    # extend list by all files within the '.ugit/refs' tree
    refs.extend( str (fp.relative_to(GIT_DIR))
                  for fp in (GIT_DIR / 'refs').rglob('*')
                  if fp.is_file()
               )

    for refname in refs:
        if not refname.startswith (prefix):
            continue
        ref = get_ref (refname, deref=deref)
        if ref.value:
            yield refname, ref


@contextmanager
def get_index ():
    """ In the context of processing the Index from JSON file, 
    the Index is returned to the caller, 
    and afterwards written back in JSON format.
    """
    index = {}

    fp = GIT_DIR / 'index'
    if fp.is_file ():
        index = json.loads (fp.read_text ())

    yield index

    fp.write_text (json.dumps (index))


def hash_object (data, type_='blob'):
    """ write file content to object database by object Id """
    obj = type_.encode () + b'\x00' + data
    oid = hashlib.sha1 (obj).hexdigest ()
    
    fp = GIT_DIR / 'objects' / oid
    if not fp.is_file ():
        fp.write_bytes(obj)
    
    return oid


def get_object (oid, expected='blob'):
    """ Fetch file content from object database by OId """
    obj = (GIT_DIR / 'objects' / oid).read_bytes()

    type_, _, content = obj.partition (b'\x00')
    type_ = type_.decode ()

    if expected is not None:
        assert type_ == expected, f'Expected {expected}, got {type_}'

    return content


def object_exists (oid):
    """ Test if object exists """
    return (GIT_DIR / 'objects' / oid).is_file() 


def fetch_object_if_missing (oid, remote_git_dir):
    """ Fetch object from remote GIT_DIR """
    if object_exists (oid):
        return

    fp = GIT_DIR / 'objects' / oid
    fp.write_bytes( (remote_git_dir / fp ).read_bytes() )


def push_object (oid, remote_git_dir):
    """ Push object to remote GIT_DIR """
    fp = GIT_DIR / 'objects' / oid
    (remote_git_dir / fp).write_bytes( fp.read_bytes() )



#!/usr/bin/env python3

# File: cli.py
# Date: 2020-12-10


import string
import subprocess
import sys
import textwrap
import typer

from pathlib import Path
from typing import List, Optional

from ugit import base
from ugit import data
from ugit import diff
from ugit import remote


# Validation helper

def is_oid (oid):
    is_hex = all (c in string.hexdigits for c in oid)
    if len (oid) == 40 and is_hex and data.object_exists (oid): 
        return oid
    else: 
        return base.get_oid (oid)

    

app = typer.Typer()


@app.command()
def init():
    """
    Initialize the UGIT repository
    """
    base.init()
    print (f'Initialized empty ugit repository in {data.GIT_DIR.absolute()}')


@app.command('hash-object')
def hash_object (file: Path = typer.Argument(..., exists=True)):
    """
    Add a single file to the repository and print it's OID
    """
    print (data.hash_object (file.read_bytes ()))


@app.command('cat-file')
def cat_file (object:  str = typer.Argument(...,  callback=is_oid)):
    """
    Display file content for a given OID 
    """
    if data.object_exists (object):
        print (data.get_object (object, expected=None).decode())


@app.command('write-tree')
def write_tree ():
    """
    Write tree from Index to the repository
    """  
    base.write_tree ()
    # print ('base.write_tree ()')


@app.command('read-tree')
def read_tree (tree: str = typer.Argument(...,  callback=is_oid)):
    """
    Read tree from repository into the Index
    """
    base.read_tree (tree)


@app.command()
def commit (message: str = typer.Option (...,  "--message", "-m")):
    """
    Commit changes to the repository
    """
    print (base.commit (message))
                 

def _print_commit (oid, commit, refs=None):
    refs_str = f' ({", ".join (refs)})' if refs else ''
    print (f'commit {oid}{refs_str}\n')
    print (textwrap.indent (commit.message, '    '))
    print ('')


@app.command()
def log (value: str = typer.Argument('@', callback=is_oid)):
    """
    Display a log of all Commits & References
    """
    refs = {}
    for refname, ref in data.iter_refs ():
        refs.setdefault (ref.value, []).append (refname)

    for oid in base.iter_commits_and_parents ({value}):
        commit = base.get_commit (oid)
        _print_commit (oid, commit, refs.get (oid))


@app.command()
def show (value: str = typer.Argument('@', callback=is_oid)):
    """
    Show differences between given and previous Commit point
    """
    commit = base.get_commit (value)
    parent_tree = None
    if commit.parents:
        parent_tree = base.get_commit (commit.parents[0]).tree

    _print_commit (value, commit)
    result = diff.diff_trees (
        base.get_tree (parent_tree), base.get_tree (commit.tree))
    sys.stdout.flush ()
    sys.stdout.buffer.write (result)


@app.command('diff')
def _diff (commit: str,
           cached: bool = typer.Option (False)):
    """
    Show the differences to current HEAD or given Commit point
    """
    oid = commit and base.get_oid (commit)

    if commit:
        # If a commit was provided explicitly, diff from it
        tree_from = base.get_tree (oid and base.get_commit (oid).tree)

    if cached:
        tree_to = base.get_index_tree ()
        if not commit:
            # If no commit was provided, diff from HEAD
            oid = base.get_oid ('@')
            tree_from = base.get_tree (oid and base.get_commit (oid).tree)
    else:
        tree_to = base.get_working_tree ()
        if not commit:
            # If no commit was provided, diff from index
            tree_from = base.get_index_tree ()

    result = diff.diff_trees (tree_from, tree_to)
    sys.stdout.flush ()
    sys.stdout.buffer.write (result)


@app.command()
def checkout (commit: str = typer.Argument('@', callback=is_oid)):
    """
    Checkout working tree based until given reference
    """
    base.checkout (commit)


@app.command()
def tag (name: str,
         oid: str = typer.Argument('@', callback=is_oid)):
    """
    Create a tag pointer to the given Commit point
    """
    base.create_tag (name, oid)


@app.command()
def branch (name: str = typer.Argument('@'),
            start_point: str = typer.Argument('@', callback=is_oid)):
    """
    Create a branch name associated to an existing Commit point
    """
    if not name:
        current = base.get_branch_name ()
        for branch in base.iter_branch_names ():
            prefix = '*' if branch == current else ' '
            print (f'{prefix} {branch}')
    else:
        base.create_branch (name, start_point)
        print (f'Branch {name} created at {start_point[:10]}')


@app.command()
def k ():
    """
    Display a diagram of Commits & References
    """
    dot = 'digraph commits {\n'

    oids = set ()
    for refname, ref in data.iter_refs (deref=False):
        dot += f'"{refname}" [shape=note]\n'
        dot += f'"{refname}" -> "{ref.value}"\n'
        if not ref.symbolic:
            oids.add (ref.value)

    for oid in base.iter_commits_and_parents (oids):
        commit = base.get_commit (oid)
        dot += f'"{oid}" [shape=box style=filled label="{oid[:10]}"]\n'
        for parent in commit.parents:
            dot += f'"{oid}" -> "{parent}"\n'

    dot += '}'
    print (dot)

    with subprocess.Popen (
            ['dot', '-Tgtk', '/dev/stdin'],
            stdin=subprocess.PIPE) as proc:
        proc.communicate (dot.encode ())


@app.command()
def status ():
    """
    List status on changed, staged or comitted files
    """
    HEAD = base.get_oid ('@')
    branch = base.get_branch_name ()
    if branch:
        print (f'On branch {branch}')
    else:
        print (f'HEAD detached at {HEAD[:10]}')

    MERGE_HEAD = data.get_ref ('MERGE_HEAD').value
    if MERGE_HEAD:
        print (f'Merging with {MERGE_HEAD[:10]}')

    print ('\nChanges to be committed:\n')
    HEAD_tree = HEAD and base.get_commit (HEAD).tree
    for path, action in diff.iter_changed_files (base.get_tree (HEAD_tree),
                                                 base.get_index_tree ()):
        print (f'{action:>12}: {path}')

    print ('\nChanges not staged for commit:\n')
    for path, action in diff.iter_changed_files (base.get_index_tree (),
                                                 base.get_working_tree ()):
        print (f'{action:>12}: {path}')


@app.command()
def reset (commit: str = typer.Argument('@', callback=is_oid)):
    """
    Reset HEAD to given Commit point
    """
    base.reset (commit)


@app.command()
def merge (commit: str = typer.Argument(...,  callback=base.get_oid)):
    """
    Merge Branch with current HEAD
    """
    base.merge (commit)


@app.command('merge-base')
def merge_base (commit1: str = typer.Argument(...,  callback=base.get_oid), 
                commit2: str = typer.Argument(...,  callback=base.get_oid)):
    """
    Merge branches based on two given commit points
    """
    print (base.get_merge_base (commit1, commit2))


@app.command()
def fetch (remote_path: Path  = typer.Argument(..., exists=True, dir_okay=True, readable=True)):
    """
    Fetch branch from a remote repository
    """
    remote.fetch (remote_path)

    
@app.command()
def push (remote_path: Path = typer.Argument (..., exists=True, dir_okay=True, readable=True),
          branch: str = typer.Argument (...)):
    """
    Push Branch to a remote repository
    """
    if branch and base.is_branch (branch):
        remote.push (str(remote_path), f'refs/heads/{branch}')
    else:
        print ('ERROR: Given branch is incorrect')


@app.command()
def add (files: List[Path]):
    """
    Add a list of files/dirs to the repository and its Index file
    """
    base.add (files)


@app.command()
def main ():
    with data.change_git_dir ('.'):
        app()


if __name__ == "__main__":
    main()


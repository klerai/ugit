# File:	ugit-test.py

# Test routines for UGIT project
# - extracted from the Notebook files:

### Test routines for data.py

def refs_test (oid):
	""" Expects the Object Id from a commit object """
	print ('''
Testing Reference Functions:
- ie. get_ref(), update_ref(), delete_ref() & iter_refs, 
''')

	ref = f'refs/tags/test1'
	oid = f'2fa33ebca44bf517df0be821fc620ca0d342a5c5'

	print ('''Set a new reference: test1
- and retrieve its value') 
''')
	update_ref (ref, RefValue (symbolic=False, value=oid))
	print (get_ref (ref).value)

	print ('''
Fetch all references and print their OIDs
''')
	for i in iter_refs (): print (i[1][1])

	print ('''
  - and delete the reference again''')
	delete_ref (ref)


def show_index ():
	print ('Retrieving the content from the json file: .ugit/index')
	print ()
	with get_index() as index: print( index)


def test_pushing (oid, remote_dir):
	""" Expects Object Id & destination path """
	print (' Testing change_git_dir() together with push_object() & get_object()')

	# oid = '47729ee8498ece441d20d936c2efb4a9c56a3cc7'
	# remote_dir = '/home/klerai/tmp1'

	print (' - insuring that the object database is available in the remote directory')
	with change_git_dir (remote_dir):
		init()

	print (' - pushing existing object to remote store,')
	push_object (oid, remote_dir)

	print (' - afterwards displaying 25 chars of its content from the remote store')
	print ()
	with change_git_dir (remote_dir):
		print( get_object (oid).decode()[:25])


#!/usr/bin/env python
#
# Copyright (c) 2004-2008, Freddie
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

'A simple web gallery written in Python.'

__author__ = 'freddie@madcowdisease.org'

import time
Started = time.time()

import os
import re
import sys
import traceback

from gallerpy import __version__, load_config, generate_thumbnails
from yats import TemplateDocument

# ---------------------------------------------------------------------------

import dircache
CACHE = {}

IMAGE_RE = re.compile(r'\.(bmp|gif|jpe|jpe?g|png)$', re.I)

# ---------------------------------------------------------------------------
# Spit out a traceback in a sane manner
def ExceptHook(etype, evalue, etb):
	lines = []
	
	lines.append('<h2>Kaboom!</h2>')
	
	lines.append('<pre>')
	
	for entry in traceback.extract_tb(etb):
		dirname, filename = os.path.split(entry[0])
		
		line = 'File "<b>%s</b>", line <b>%d</b>, in <b>%s</b>' % (
			filename, entry[1], entry[2])
		lines.append(line)
		line = '  %s' % entry[-1]
		lines.append(line)
	
	lines.append('')
	
	for line in traceback.format_exception_only(etype, evalue):
		line = line.replace('\n', '')
		lines.append(line)
	
	lines.append('</pre>')
	
	# Now spit it out
	ShowError('\n'.join(lines))
	
	sys.exit(0)

# ---------------------------------------------------------------------------

def ShowError(text, *args):
	if args:
		text = text % args
	
	tmpl = GetTemplate('Error!')
	
	tmpl.extract('show_text')
	tmpl.extract('show_dirs')
	tmpl.extract('show_images')
	tmpl.extract('show_image')
	
	tmpl['error'] = text
	tmpl['elapsed'] = '%.3fs' % (time.time() - Started)
	
	print 'Content-type: text/html'
	print
	print tmpl
	
	return None

# ---------------------------------------------------------------------------

def main(env=os.environ, started=Started, scgi=0):
	global Started, UsingSCGI
	Started = started
	UsingSCGI = scgi
	
	t1 = time.time()
	
	# Some naughty globals
	global Conf, Paths, Warnings
	Paths = {}
	Warnings = []
	
	# We need these
	global SCRIPT_FILENAME, SCRIPT_NAME
	SCRIPT_FILENAME = env.get('SCRIPT_FILENAME', None)
	SCRIPT_NAME = env.get('SCRIPT_NAME', None)
	
	# Find our config
	if SCRIPT_FILENAME is None or SCRIPT_NAME is None:
		return ShowError('CGI environment is broken!')
	
	config_file = os.path.join(os.path.dirname(SCRIPT_FILENAME), 'gallerpy.conf')
	if not os.path.isfile(config_file):
		return ShowError('config file is missing!')
	
	# Parse our config
	tc1 = time.time()
	Conf = load_config(config_file)
	tc2 = time.time()
	
	# Work out some paths
	if not ('thumbs_local' in Conf and 'thumbs_web' in Conf):
		Conf['thumbs_web'], Conf['thumbs_local'] = GetPaths('thumbs')
		if Conf['thumbs_local'] is None:
			return ShowError("Can't find your thumbnail directory!")
	
	if Conf['use_resized']:
		if not ('resized_local' in Conf and 'resized_web' in Conf):
			Conf['resized_web'], Conf['resized_local'] = GetPaths('_resized')
			if Conf['resized_local'] is None:
				return ShowError("Can't find your resized image directory!")
	
	Paths['folder_image'] = GetPaths(Conf['folder_image'])[0] or 'folder.png'
	
	Conf['template'] = os.path.join(os.path.dirname(SCRIPT_FILENAME), Conf['template'])
	
	# Work out what they're after
	path_info = env.get('PATH_INFO', None) or '.'
	
	# Don't want a starting or ending seperator
	if path_info.startswith('/'):
		path_info = path_info[1:]
	
	if path_info.endswith('/'):
		path_info = path_info[:-1]
	
	# If there's an image on the end, we want it
	image_name = None
	
	bits = list(path_info.split('/'))
	
	# See if they want a full image
	global FullImage
	FullImage = 0
	
	if bits[-1] == '_full_':
		blah = bits.pop(-1)
		FullImage = 1
	
	# See if they're after an image
	m = IMAGE_RE.search(bits[-1])
	if m:
		image_name = bits.pop(-1)
		path_info = '/'.join(bits) or '.'
	
	# Don't let people go into hidden dirs
	if len(bits) > 0:
		if bits[-1] in Conf['hide_dirs']:
			return ShowError('Access denied: %s', path_info)
	
	# If we have a different local root, we need to change path
	if ('root_local' in Conf and 'root_web' in Conf):
		os.chdir(Conf['root_local'])
	
	# Check the path to make sure it's valid
	image_dir = GetPaths(path_info)[1]
	if image_dir is None:
		return ShowError('Path does not exist: %s', path_info)
	
	# We need to know what the current dir is
	Paths['current'] = path_info or '.'
	
	t2 = time.time()
	
	# Now that we've done all that, update the thumbnails
	data = UpdateThumbs(image_name)
	
	t3 = time.time()
	
	# If we have an image name, try to display it
	if image_name:
		tmpl = DisplayImage(data, image_name)
	
	# Or we could just display the directory
	else:
		tmpl = DisplayDir(data)
	
	# An error occurred
	if tmpl is None:
		return
	
	t4 = time.time()
	
	# Work out how long it took
	tmpl['elapsed'] = '%.3fs' % (time.time() - started)
	
	# If we had any warnings, add those
	if Warnings:
		tmpl['error'] = '<br />\n'.join(Warnings)
	else:
		tmpl.extract('show_error')
	
	t5 = time.time()
	
	# We are HTML!
	if Conf['show_header']:
		encoding = Conf.get('encoding', None)
		if encoding is not None:
			print 'Content-type: text/html; charset=%s' % (encoding)
		else:
			print 'Content-type: text/html'
	
	# If we're using GZIP, it might be time to squish
	if Conf['use_gzip'] and env.get('HTTP_ACCEPT_ENCODING', '').find('gzip') >= 0:
		import cStringIO
		import gzip
		
		zbuf = cStringIO.StringIO()
		gzip.GzipFile(mode='wb', fileobj=zbuf, compresslevel=Conf['use_gzip']).write(str(tmpl))
		
		# Spit out our gzip headers
		print 'Content-Encoding: gzip'
		print 'Content-Length: %d' % (zbuf.tell())
		print
		print zbuf.getvalue()
	
	# Just normal output please
	else:
		print
		print tmpl
	
	# Debug info
	if False:
		print 'startup: %.4fs<br />\n' % (t1 - Started)
		print 'startup(conf): %.4fs<br />\n' % (tc2 - tc1)
		print 'parse_env: %.4fs<br />\n' % (t2 - t1)
		print 'thumbs: %.4fs<br />\n' % (t3 - t2)
		print 'display: %.4fs<br />\n' % (t4 - t3)
		print 'finish_tmpl: %.4fs<br />\n' % (t5 - t4)
		print 'print_tmpl: %.4fs<br />\n' % (time.time() - t5)

# ---------------------------------------------------------------------------
# Update the thumbnails for a directory. Returns a dictionary of data
def UpdateThumbs(image_name):
	# Ask dircache for a list of files
	files = dircache.listdir(Paths['current'])
	
	if UsingSCGI:
		if Paths['current'] in CACHE:
			if files is CACHE[Paths['current']][0]:
				return CACHE[Paths['current']][1]
	
	# Get a sorted list of filenames
	lfiles = list(files)
	if Conf['sort_alphabetically']:
		temp = [(f.lower(), f) for f in lfiles]
		temp.sort()
		lfiles = [f[1] for f in temp]
		del temp
	else:
		lfiles.sort()
	
	# Initialise the data structure
	data = {
		'dirs': [],
		'images': [],
	}
	
	if Paths['current'] == '.':
		try:
			lfiles.remove(Conf['folder_image'])
		except ValueError:
			pass
	
	# If they want just a single image, we only have to update 1-3 thumbs...
	# unless we're using SCGI, then we should always update the whole
	# directory to save time later.
	if image_name and not UsingSCGI:
		for i in range(len(lfiles)):
			if lfiles[i] == image_name:
				newfiles = []
				
				# Search backwards for a valid image for the prev link
				if i > 0:
					for j in range(i-1, -1, -1):
						if IMAGE_RE.search(lfiles[j]):
							newfiles.append(lfiles[j])
							break
				
				# This image
				newfiles.append(lfiles[i])
				
				# Search forwards for a valid image for the next link
				if i < (len(lfiles) - 1):
					for j in range(i+1, len(lfiles)):
						if IMAGE_RE.search(lfiles[j]):
							newfiles.append(lfiles[j])
							break
				
				lfiles = newfiles
				break
	
	# Time to generate stuff!
	newthumbs, data['dirs'], data['images'], warnings = generate_thumbnails(Conf, Paths['current'], lfiles)
	
	# If it's not the root dir, add '..' to the list of dirs
	if Paths['current'] != '.':
		data['dirs'].insert(0, '..')
	
	# If we had any warnings, stick them into the errors thing
	Warnings.extend(warnings)
	
	# If we're using SCGI, cache the info
	if UsingSCGI:
		CACHE[Paths['current']] = [files, data]
	
	# Throw the info back
	return data

# ---------------------------------------------------------------------------
# Spit out a nicely formatted listing of a directory
def DisplayDir(data):
	# Get our template
	if Paths['current'] == '.':
		nicepath = '/'
	else:
		nicepath = '/%s' % Paths['current']
	
	tmpl = GetTemplate(nicepath)
	
	# If we have some dirs, display them
	dirs = []
	
	if data['dirs']:
		for directory in data['dirs']:
			# Skip hidden dirs
			if directory in Conf['hide_dirs']:
				continue
			
			# Parent dir
			elif directory == '..':
				blat = os.path.join(Paths['current'], '..')
				dir_link = os.path.normpath(blat)
			
			else:
				if Paths['current'] == '.':
					dir_link = directory
				else:
					dir_link = '%s/%s' % (Paths['current'], directory)
			
			row = {
				'dir_desc': directory.replace('_', ' '),
				'dir_link': '%s/%s' % (SCRIPT_NAME, dir_link),
				'folder_img': Paths['folder_image'],
			}
			
			dirs.append(row)
	
	# Extract stuff we don't need
	headpath = os.path.join(Paths['current'], Conf['header_file'])
	if os.path.isfile(headpath):
		tmpl['header_text'] = open(headpath, 'r').read()
	else:
		tmpl.extract('show_text')
	
	if dirs:
		tmpl['dirs'] = dirs
	else:
		tmpl.extract('show_dirs')
	
	tmpl.extract('show_image')
	
	# If we have some images, display those
	images = []
	
	if data['images']:
		for image_name, image_file, image_size, image_width, image_height, thumb_name, thumb_width, thumb_height, resized_width, resized_height in data['images']:
			row = {}
			
			# Maybe add some extra stuff
			parts = []
			
			if Conf['thumb_name']:
				part = '<p>%s</p>' % image_name.replace('_', ' ')
				parts.append(part)
			
			if Conf['thumb_dimensions']:
				part = '<p class="small">(%s x %s)</p>' % (image_width, image_height)
				parts.append(part)
			
			if Conf['thumb_size']:
				part = '<p class="small">%s</p>' % (image_size)
				parts.append(part)
			
			row['extra'] = ''.join(parts)
			
			row['image_link'] = '%s/%s' % (SCRIPT_NAME, Quote(image_file))
			
			row['thumb_img'] = '%s/%s' % (Conf['thumbs_web'], thumb_name)
			
			row['divbit'], row['thumb_params'] = ThumbImgParams(thumb_width, thumb_height)
			
			row['alt'] = 'Thumbnail for %s' % (image_name)
			
			images.append(row)
	
	if images:
		tmpl['images'] = images
	else:
		tmpl.extract('show_images')
	
	return tmpl

# ---------------------------------------------------------------------------
# Display an image page
def DisplayImage(data, image_name):
	# See if the image exists
	n = None
	for i in range(len(data['images'])):
		if data['images'][i][0] == image_name:
			n = i
			break
	
	if n is None:
		return ShowError('File does not exist: %s' % image_name)
	
	# Set up some path info and get our template
	if Paths['current'] == '.':
		nicepath = '/'
	else:
		nicepath = '/%s' % Paths['current']
	nicepath = '%s/%s' % (nicepath, image_name)
	
	tmpl = GetTemplate(nicepath)
	
	# Extract stuff we don't need
	tmpl.extract('show_text')
	tmpl.extract('show_dirs')
	tmpl.extract('show_images')
	
	# Work out the prev/next images too
	this = data['images'][n]
	
	# for image_name, image_file, image_size, image_width, image_height, thumb_name, thumb_width,
	# thumb_height, resized_width, resized_height in data['images']:
	
	# Previous image
	if n > 0:
		prev = data['images'][n-1]
		prev_enc = Quote(prev[1])
		divbit, img_params = ThumbImgParams(prev[6], prev[7])
		
		tmpl['prevlink'] = '<div%s><a href="%s/%s"><img src="%s/%s" %s><br />%s</a></div>' % (
			divbit, SCRIPT_NAME, prev_enc, Conf['thumbs_web'], prev[5], img_params, prev[0])
	
	# Next image
	if data['images'][n+1:n+2]:
		next = data['images'][n+1]
		next_enc = Quote(next[1])
		divbit, img_params = ThumbImgParams(next[6], next[7])
		
		tmpl['nextlink'] = '<div%s><a href="%s/%s"><img src="%s/%s" %s><br />%s</a></div>' % (
			divbit, SCRIPT_NAME, next_enc, Conf['thumbs_web'], next[5], img_params, next[0])
	
	# If there's a resized one, we'll display that
	if Conf['use_resized'] and this[-2] and this[-1] and not FullImage:
		tmpl['this_img'] = '    (click image for full size)<br /><a href="%s/%s/_full_"><img src="%s/%s" width="%s" height="%s" alt="%s"></a>' % (
			SCRIPT_NAME, this[1], Conf['resized_web'], this[5], this[-2], this[-1], this[0]
		)
	# Guess not, just display the image
	else:
		tmpl['this_img'] = '    <img src="%s" width="%s" height="%s" alt="%s">' % (
			Quote(GetPaths(this[1])[0]), this[3], this[4], this[0])
	
	# Work out what extra info we need to display
	parts = []
	
	if Conf['image_name']:
		part = '    <h2>%s</h2>\n' % (this[0])
		parts.append(part)
	if Conf['image_dimensions']:
		part = '    <p class="small">%s x %s</p>\n' % (this[3], this[4])
		parts.append(part)
	if Conf['image_size']:
		part = '    <p class="small">%s</p>\n' % (this[2])
		parts.append(part)
	
	tmpl['extra'] = ''.join(parts)
	
	tmpl['dir_path'] = '%s/%s' % (SCRIPT_NAME, Paths['current'])
	tmpl['folder_img'] = Paths['folder_image']
	
	return tmpl

# ---------------------------------------------------------------------------
# Get a (URL, local) path for something
def GetPaths(path):
	if ('root_local' in Conf and 'root_web' in Conf):
		dsf = Conf['root_local']
		dsn = Conf['root_web']
	else:
		dsf = os.path.dirname(SCRIPT_FILENAME)
		dsn = os.path.dirname(SCRIPT_NAME)
	
	# Absolute path
	if path.startswith(os.sep):
		return (path, None)
	# HTTP URL
	elif path.startswith('http://'):
		return (path, None)
	# Relative path
	else:
		localpath = os.path.normpath(os.path.join(dsf, path))
		
		# They're going wandering, or it doesn't exist
		if not localpath.startswith(dsf) or not os.path.exists(localpath):
			return (None, None)
		
		else:
			remotepath = os.path.join(dsn, path)
			return (remotepath, localpath)

# ---------------------------------------------------------------------------
# Return a string usable as <img> tag parameters
def ThumbImgParams(width, height):
	divbit = ''
	params = 'width="%s" height="%s"' % (width, height)
	
	if Conf['thumb_pad']:
		pad_top = Conf['thumb_height'] - height
		if pad_top > 0:
			divbit = ' style="padding-top: %spx;"' % (pad_top)
	
	return divbit, params

# ---------------------------------------------------------------------------
# Safely quote a string for a URL
def Quote(s):
	for char in (';?:@&=+$#, '):
		s = s.replace(char, '%%%02X' % ord(char))
	return s

# ---------------------------------------------------------------------------

def GetTemplate(title=None):
	if title == 'Error!':
		defpath = os.path.join(os.path.split(SCRIPT_FILENAME)[0], 'default.tmpl')
		tmpl = TemplateDocument(defpath)
	else:
		tmpl = TemplateDocument(Conf['template'])
	
	# Build our shiny <title>
	gallery_name = Conf.get('gallery_name', 'GallerPy %s' % __version__)
	
	if title:
		tmpl['title'] = '%s :: %s' % (gallery_name, title)
	else:
		tmpl['title'] = '%s' % (gallery_name)
	
	# Are we showing the header?
	if Conf['show_header']:
		# Find our CSS file
		css_file = GetPaths(Conf['css_file'])[0]
		if css_file is None:
			css_file = 'default.css'
		tmpl['css_file'] = css_file
		
		# Work out the box size for thumbnails
		tmpl['thumb_width'] = Conf['thumb_width'] + 10
		
		add = (Conf['thumb_name'] + Conf['thumb_dimensions'] + Conf['thumb_size']) * 16
		tmpl['thumb_height'] = Conf['thumb_height'] + 16 + add
	# Guess not
	else:
		tmpl.extract('show_header')
	
	# Our version!
	tmpl['version'] = __version__
	
	# Are we not showing the footer?
	if not Conf['show_footer']:
		tmpl.extract('show_footer')
	
	# And send it back
	return tmpl

# ---------------------------------------------------------------------------

if __name__ == '__main__':
	# Replace our exception handler with a magic one
	sys.excepthook = ExceptHook
	
	main()

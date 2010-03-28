#!/usr/bin/env python
#
#    weewx --- A simple, high-performance weather station server
#
#    Copyright (c) 2009 Tom Keffer <tkeffer@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    $Revision$
#    $Author$
#    $Date$
#
""" Customized weewx setup script.

    In addition to the normal setup script duties, this script does the
    following:

 1. When building a source distribution ('sdist') it checks for
    password information in the configuration file weewx.conf

 2. It merges any existing weewx.conf configuration files into the new, thus
    preserving any user changes.
    
 3. It sets the option ['Station']['WEEWX_ROOT'] in weewx.conf to reflect
    the actual installation directory (as set in setup.cfg or specified
    in the command line to setup.py install)

 4. It backups up any pre-existing skin subdirectory
"""

from distutils.core import setup, Command
from distutils.command.install_data import install_data
from distutils.command.install_lib  import install_lib
from distutils.command.sdist import sdist

import sys
import os
import os.path
import re
import time
import tempfile
import shutil
import configobj

from weewx import __version__ as VERSION

class My_install_lib(install_lib):
    """Specialized version of install_lib
    
    This version:
    
    - Backs up the old ./bin subdirectory before installing.
    """ 

    def run(self):
        if os.path.exists(self.install_dir):
            bin_backupdir = backup(self.install_dir)
            print "Backed up bin subdirectory to %s" % bin_backupdir

        # Run the superclass's run:
        install_lib.run(self)
        
class My_install_data(install_data):
    """Specialized version of install_data 
    
    This version: 
    
      - Sets WEEWX_ROOT in the configuration file to reflect the
        actual installation root directory;
      - Merges an old configuration file into a new,
        thus preserving any changes made by the user;
      - Backs up the old skin directory;
      - Massages the daemon start up script to reflect the choice
        of WEEWX_ROOT        
    """
    
    def copy_file(self, f, install_dir, **kwargs):
        rv = None
        # If this is the configuration file, then merge it instead
        # of copying it
        if f == 'weewx.conf':
            rv = self.massageConfigFile(f, install_dir, **kwargs)
        elif f in ('start_scripts/Debian/weewx', 'start_scripts/SuSE/weewx'):
            rv = self.massageStartFile(f, install_dir, **kwargs)
        else:
            rv = install_data.copy_file(self, f, install_dir, **kwargs)
        return rv
    
    def run(self):
            
        # Back up the old skin directory if it exists
        skin_dir = os.path.join(self.install_dir, 'skins')
        if os.path.exists(skin_dir):
            skin_backupdir = backup(skin_dir)
            print "Backed up skins subdirectory to %s" % skin_backupdir
            
        # Run the superclass's run():
        install_data.run(self)
        
        # If the file #upstream.last exists, delete it, as it is no longer used.
        try:
            os.remove(os.path.join(self.install_dir, 'public_html/#upstream.last'))
        except:
            pass
            
        # If the file $WEEWX_ROOT/readme.htm exists, delete it. It's
        # the old readme (since replaced with docs/readme.htm)
        try:
            os.remove('readme.htm')
        except:
            pass

    def massageConfigFile(self, f, install_dir, **kwargs):
        """Merges any old config file into the new one, and sets WEEWX_ROOT
        
        If an old configuration file exists, it will merge the contents
        into the new file. It also sets variable ['Station']['WEEWX_ROOT']
        to reflect the installation directory"""
        
        # The path name of the final output file:
        outname = os.path.join(install_dir, os.path.basename(f))
        
        # Create a ConfigObj using the new contents:
        newconfig = configobj.ConfigObj(f)
        newconfig.indent_type = '    '
        new_version_number = VERSION.split('.')
        
        # Check to see if there is an existing config file.
        # If so, merge its contents with the new one
        if os.path.exists(outname):
            oldconfig = configobj.ConfigObj(outname)
            old_version = oldconfig.get('version')
            # If the version number does not appear at all, then
            # assume a very old version:
            if not old_version: old_version = '1.0.0'
            old_version_number = old_version.split('.')
            # Do the merge only for versions >= 1.6
            if old_version_number[0:2] >= ['1','6']:
                # Any user changes in oldconfig will overwrite values in newconfig
                # with this merge
                newconfig.merge(oldconfig)

        # Make sure WEEWX_ROOT reflects the choice made in setup.cfg:
        newconfig['Station']['WEEWX_ROOT'] = self.install_dir
        # Add the version:
        newconfig['version'] = VERSION
        
        # Get a temporary file:
        tmpfile = tempfile.NamedTemporaryFile("w", 1)
        
        # Write the new configuration file to it:
        newconfig.write(tmpfile)
        
        # Back up the old config file if it exists:
        if os.path.exists(outname):
            backup_path = backup(outname)
            print "Backed up old configuration file as %s" % backup_path
            
        # Now install the temporary file (holding the merged config data)
        # into the proper place:
        rv = install_data.copy_file(self, tmpfile.name, outname, **kwargs)
        
        # Set the permission bits unless this is a dry run:
        if not self.dry_run:
            shutil.copymode(f, outname)

        return rv
        
    def massageStartFile(self, f, install_dir, **kwargs):

        outname = os.path.join(install_dir, os.path.basename(f))
        sre = re.compile(r"WEEWX_ROOT\s*=")

        infile = open(f, "r")
        tmpfile = tempfile.NamedTemporaryFile("w", 1)
        
        for line in infile:
            if sre.match(line):
                tmpfile.writelines("WEEWX_ROOT=%s\n" % self.install_dir)
            else:
                tmpfile.writelines(line)
        
        rv = install_data.copy_file(self, tmpfile.name, outname, **kwargs)

        # Set the permission bits unless this is a dry run:
        if not self.dry_run:
            shutil.copymode(f, outname)

        return rv

def backup(filepath):
    # Sometimes the target has a trailing '/'. This will take care of it:
    filepath = os.path.normpath(filepath)
    newpath = filepath + time.strftime(".%Y%m%d%H%M%S")
    os.rename(filepath, newpath)
    return newpath

class My_sdist(sdist):
    """Specialized version of sdist which checks for password information in distribution

    See http://epydoc.sourceforge.net/stdlib/distutils.command.sdist.sdist-class.html
    for possible sdist instance methods."""

    def copy_file(self, f, install_dir, **kwargs):
        """Specialized version of copy_file.

        Return a tuple (dest_name, copied): 'dest_name' is the actual name of
        the output file, and 'copied' is true if the file was copied (or would
        have been copied, if 'dry_run' true)."""
        # If this is the configuration file, then massage it to eliminate
        # the password info
        if f == 'weewx.conf':
            # If we're working with the configuration file, make sure it doesn't
            # have any private data in it.
            config = configobj.ConfigObj(f)

            if config.has_key('FTP') and config['FTP'].has_key('password'):
                sys.stderr.write("\n*** FTP password found in configuration file. Aborting ***\n\n")
                exit()

            if config.has_key('Wunderground') and config['Wunderground'].has_key('password'):
                sys.stderr.write("\n*** Wunderground password found in configuration file. Aborting ***\n\n")
                exit()
        return sdist.copy_file(self, f, install_dir, **kwargs)

setup(name='weewx',
      version=VERSION,
      description='The weewx weather system',
      long_description="The weewx weather system manages a Davis VantagePro "
      "weather station. It generates plots, statistics, and HTML pages of the "
      "current and historical weather",
      author='Tom Keffer',
      author_email='tkeffer@gmail.com',
      url='http://www.weewx.com',
      packages    = ['weewx', 'weeplot', 'weeutil', 'examples'],
      py_modules  = ['daemon'],
      scripts     = ['configure.py', 'weewxd.py'],
      data_files  = [('',                           ['CHANGES.txt', 'LICENSE.txt', 'README', 'weewx.conf']),
                     ('docs',                       ['docs/customizing.htm', 'docs/readme.htm', 
                                                     'docs/sheeva.htm', 'docs/upgrading.htm',
                                                     'docs/daytemp_with_avg.png', 'docs/weekgustoverlay.png']),
                     ('skins/Ftp',                  ['skins/Ftp/skin.conf']),
                     ('skins/Standard/backgrounds', ['skins/Standard/backgrounds/band.gif']),
                     ('skins/Standard/NOAA',        ['skins/Standard/NOAA/NOAA-YYYY.txt.tmpl', 'skins/Standard/NOAA/NOAA-YYYY-MM.txt.tmpl']),
                     ('skins/Standard',             ['skins/Standard/index.html.tmpl', 'skins/Standard/month.html.tmpl',
                                                     'skins/Standard/skin.conf', 'skins/Standard/week.html.tmpl',
                                                     'skins/Standard/weewx.css', 'skins/Standard/year.html.tmpl']), 
                     ('start_scripts',              ['start_scripts/Debian/weewx', 'start_scripts/SuSE/weewx'])],
      requires    = ['configobj(>=4.5)', 'pyserial(>=1.35)', 'Cheetah(>=2.0)', 'pysqlite(>=2.5)', 'PIL(>=1.1.6)'],
      cmdclass    = {"install_data" : My_install_data,
                     "install_lib"  : My_install_lib,
                     "sdist" :        My_sdist}
      )

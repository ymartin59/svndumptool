#===============================================================================
#
# Copyright (C) 2003 Martin Furter <mf@rola.ch>
#
# This file is part of SvnDumpTool
#
# SvnDumpTool is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# SvnDumpTool is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SvnDumpTool; see the file COPYING.  If not, write to
# the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#
#===============================================================================

from optparse import OptionParser
import re
import md5

from file import SvnDumpFile
from node import SvnDumpNode

def eolfix_callback_prop( dumpfile, node, textfiles ):
    """Check for property and do conversion if needed."""

    # do we allready know that it is a textfile ?
    if textfiles.has_key( node.get_path() ):
        # +++ should i check mime-type here ?
        if node.get_action() == "delete":
            del textfiles[node.get_path()]
        return True

    # handle copy-from-path ??? +++

    # check properties
    properties = node.get_properties()
    if properties == None:
        return False
    if not properties.has_key("svn:eol-style"):
        return False

    # is a text file, add to the list
    textfiles[node.get_path()] = dumpfile.get_rev_nr()
    return True

def eolfix_callback_regexp( dumpfile, node, expressions ):
    """Check regexp list and do conversion if needed."""

    for re in expressions:
        if re.search( node.get_path() ) != None:
            return True
    return False

class SvnDumpEolFix:
    """A class for fixing mixed EOL style files in a svn dump file."""

    def __init__( self ):

        # input file name
        self.__in_file = ""
        # output file name
        self.__out_file = ""
        # dry-run, do not create an output file
        self.__dry_run = True
        # (do not) set eol-style on text files
        self.__eol_style = None
        # fix types
        self.__fix = 0
        # fix types for rev/path pairs
        self.__fix_rev_path = {}
        # warning file obj
        self.__warning_file = None
        # temp directory
        self.__temp_dir = "./"

        # temp files
        self.__temp_file_max_nr = 0
        self.__temp_file_nr = 0

    def set_input_file( self, filename ):
        """Sets the input dump file name."""
        self.__in_file = filename

    def set_output_file( self, filename ):
        """Sets the output dump file name and clears the dry-run flag."""
        self.__out_file = filename
        self.__dry_run = False

    def set_mode_prop( self ):
        """Sets mode to 'prop'.

            in this mode SvnDumpEolFix assumes text files have the property
            svn:eol-style set."""
        self.__is_text_file = eolfix_callback_prop
        self.__is_text_file_params = {}

    def set_mode_regexp( self, expressions ):
        """Sets mode to regexp.

            In this mode every file which matches at least one of the regexps
            is treated as text file."""
        self.__is_text_file = eolfix_callback_regexp
        self.__is_text_file_params = []
        for expr in expressions:
            self.__is_text_file_params.append( re.compile( expr ) )

    def set_mode_callback( self, callback, parameter ):
        """Sets mode to callback.

            ++++"""

        self.__is_text_file = callback
        self.__is_text_file_params = parameter

    def set_eol_style( self, eolstyle ):
        """Enable/disable setting eol-style on text files.
        
            If eolstyle is None do not set svn:eol-style, else set it
            to the given value."""
        self.__eol_style = eolstyle

    def set_fix_options( self, fix ):
        """Set what to fix.

            fix is a string containing comma separated options.
            valid values are:
             'CRLF'   replace CRLF by LF
             'CR'     replace CR by LF
             'RemCR'  remove CR"""
        self.__fix = self.__parse_fix_option( fix )

    def set_fix_for_rev_file( self, fixrevfile ):
        """Set what to fix for a given revision/file.

            fixrevpath is a string containing colon separated the
            fix option, revsision number and path of a file."""
        parts = fixrevfile.split( ":", 2 )
        if len( parts ) != 3:
            print "wrong number of fiels for fixrevfile option."
            return
        key = ( int( parts[1] ), parts[2] )
        self.__fix_rev_path[key] = self.__parse_fix_option( parts[0] )
        print key, self.__fix_rev_path[key]

    def __parse_fix_option( self, fixstr ):
        """Parses a string containing comma separated fix options."""
        fix = 0
        for f in fixstr.split( ',' ):
            if f == "CRLF":
                fix |= 1
            elif f == "CR":
                fix |= 2
            elif f == "RemCR":
                fix |= 4
        return fix

    def set_warning_file( self, warnfile ):
        """Sets the filename for writing warnings into."""
        if self.__warning_file != None:
            self.__warning_file.close()
        self.__warning_file = open( warnfile )
        self.__warning_file.write( "#/bin/sh\n" )
        self.__warning_file.write( "\n" )
        self.__warning_file.write( "SVN=svn\n" )
        self.__warning_file.write( "TMP=tmp\n" )
        self.__warning_file.write( "REPOS=file:///tmp/repos\n" )
        self.__warning_file.write( "\n" )

    def set_temp_dir( self, tmpdir ):
        """Sets the the directory for temporary files."""
        if tmpdir[-1] != "/":
            tmpdir += "/"
        self.__temp_dir = tmpdir

    def execute( self ):
        """Executes the EolFix."""

        # +++ catch exception and return errorcode
        srcdmp = SvnDumpFile()
        srcdmp.open( self.__in_file )

        dstdmp = None

        hasrev = srcdmp.read_next_rev()
        if hasrev:
            if not self.__dry_run:
                dstdmp = SvnDumpFile()
                if srcdmp.get_rev_nr() == 0:
                    # create new dump with revision 0
                    dstdmp.create_with_rev_0( self.__out_file,
                                              srcdmp.get_uuid(),
                                              srcdmp.get_rev_date_str() )
                    hasrev = srcdmp.read_next_rev()
                else:
                    # create new dump starting with the same revNr
                    # as the input dump file
                    dstdmp.create_with_rev_n( self.__out_file,
                                              srcdmp.get_uuid(),
                                              srcdmp.get_rev_nr() )
            # now copy all the revisions
            while hasrev:
                print "\n\n*** r%d ***\n" % srcdmp.get_rev_nr()
                self.__process_rev( srcdmp, dstdmp )
                hasrev = srcdmp.read_next_rev()

    def __process_rev( self, srcdmp, dstdmp ):
        """Process one revision."""

        # clear temp file nr (overwrite old files)
        self.__temp_file_nr = 0

        # add revision and revprops
        if dstdmp != None:
            dstdmp.add_rev( srcdmp.get_rev_props() )

        # process nodes
        index = 0
        nodeCount = srcdmp.get_node_count()
        while index < nodeCount:
            node = srcdmp.get_node( index )
            print "  '%s'" % node.get_path()
            istextfile = self.__is_text_file( srcdmp, node,
                                              self.__is_text_file_params )
            if istextfile and node.has_text():
                node = self.__convert_eol( node, srcdmp.get_rev_nr() )
            # +++ is node.has_properties a good enough test?
            # maybe i have to save the properties of each node and
            # use them here?
            if self.__eol_style != None and node.has_properties():
                if istextfile:
                    node.set_property( "svn:eol-style", self.__eol_style )
            if dstdmp != None:
                dstdmp.add_node( node )
            index = index + 1

    def __convert_eol( self, node, revnr ):
        """Convert EOL of a node"""

        if node.get_text_length == -1:
            # no text
            print "    is_text"
            return node

        # search for CR
        need_conv = False
        handle = node.text_open()
        data = node.text_read( handle )
        while len(data) > 0:
            if data.find( "\r" ) != -1:
                # found one, need to convert the file
                need_conv = True
                break
            data = node.text_read( handle )
        fix = self.__fix
        if need_conv:
            # special fix option for rev/file ?
            key = ( revnr, node.get_path() )
            if self.__fix_rev_path.has_key( key ):
                fix = self.__fix_rev_path[key]
            print "    is_text, convert (fix option %d)" % fix
            if self.__dry_run or fix == 0:
                # do not convert with --dry-run or when there's nothing to fix
                need_conv = False
        else:
            print "    is_text"
        if need_conv:
            # do the conversion
            node.text_reopen( handle )
            outfilename = self.__temp_file_name()
            outfile = open( outfilename, "w+" )
            outlen = 0
            md = md5.new()
            data = node.text_read( handle )
            carry = ""
            warning_printed = False
            while len(data) > 0:
                if len(carry) != 0:
                    data = carry + data
                n = len( data ) - 1
                carry = data[n]
                if carry == "\r":
                    data = data[:n]
                else:
                    carry = ""
                if fix & 1 != 0:
                    data = data.replace( "\r\n", "\n" )
                if fix & 2 != 0:
                    data = data.replace( "\r", "\n" )
                if fix & 4 != 0:
                    data = data.replace( "\r", "" )
                if not warning_printed and data.find( "\r" ) >= 0:
                    warning_printed = True
                    print "    WARNING: file still contains CR"
                    print "      file: '%s'" % node.get_path()
                    if self.__warning_file != None:
                        self.__warning_file.write(
                                "# WARNING: file still contains CR\n" )
                        file = node.get_path()
                        while file[0] == "/":
                            file = file[1:]
                        tmpfile = file.replace( "/", "__" )
                        cmd = '$SVN cat -r %d "$REPOS/%s" > "%s"\n' % \
                            ( revnr, node.get_path(), tmpfile )
                        self.__warning_file.write( cmd )
                md.update( data )
                outfile.write( data )
                outlen = outlen + len( data )
                data = node.text_read( handle )
            if len( carry ) != 0:
                if fix & 2 != 0:
                    carry = "\n"
                elif fix & 4 != 0:
                    carry = ""
                outfile.write( carry )
                md.update( carry )
                outlen += len( carry )
            outfile.close()
            newnode = SvnDumpNode( node.get_path(), node.get_action(),
                                   node.get_kind() )
            if node.has_copy_from():
                newnode.set_copy_from( node.get_copy_from_path(),
                                       node.get_copy_from_rev() )
            if node.has_properties():
                newnode.set_properties( node.get_properties() )
            newnode.set_text_file( outfilename, outlen, md.hexdigest() )
        else:
            newnode = node

        node.text_close( handle )
        return newnode

    def __temp_file_name( self ):
        """Create temp file name"""
        self.__temp_file_nr = self.__temp_file_nr + 1
        if self.__temp_file_nr > self.__temp_file_max_nr:
            self.__temp_file_max_nr = self.__temp_file_nr
        return "%stmpnode%d" % ( self.__temp_dir, self.__temp_file_nr )


def svndump_eol_fix_cmdline( appname, args ):
    """cmdline..."""

    usage = "usage: %s [options] src [dst]" % appname
    parser = OptionParser( usage=usage, version="%prog 0.1" )
    parser.add_option( "-E", "--eol-style",
                       action="store", dest="eolstyle", default=None,
                       type="choice", choices=[ "native", "LF", "CRLF", "CR" ],
                       help="add svn:eol-style property to text files, "
                            "the value can be 'native', 'LF', 'CRLF' or 'CR'" )
    parser.add_option( "-f", "--fix",
                       action="store", dest="fix",
                       type="string", default="CRLF",
                       help="a comma separated list of what (and how) to fix, "
                            "can be a combination of "
                            "'CRLF', 'CR' and 'RemCR'. If 'CR' and 'RemCR' "
                            "both specified 'RemCR' is ignored. 'CRLF' and "
                            "'CR' mean replace them by LF, 'RemCR' means "
                            "remove CR's." )
    parser.add_option( "-F", "--fix-rev-path",
                       action="append", dest="fixrevpath",
                       type="string",
                       help="a colon separated list of fix option, revision "
                            "number and path of a file." )
    parser.add_option( "-m", "--mode",
                       action="store", dest="mode", default="prop",
                       type="choice", choices=[ "prop", "regexp" ],
                       help="text file detection mode: one of "
                            "'prop' [default], 'regexp'" )
    parser.add_option( "-r", "--regexp",
                       action="append", dest="regexp",
                       help="regexp for matching text file names" )
    parser.add_option( "-t", "--temp-dir",
                       action="store", dest="tmpdir",
                       type="string",
                       help="directory for temporary files." )
    parser.add_option( "-w", "--warn-file",
                       action="store", dest="warnfile",
                       type="string",
                       help="file for storing the warnings." )
    parser.add_option( "--dry-run",
                       action="store_true", dest="dry_run", default=False,
                       help="just show what would be done but don't do it" )
    (options, args) = parser.parse_args( args )

    eolfix = SvnDumpEolFix()

    if len( args ) < 1 or len( args ) > 2:
        print "please specify one source and optionally one destination file."
        return 1
    eolfix.set_input_file( args[0] )
    if len( args ) == 2:
        eolfix.set_output_file( args[1] )
    if options.mode == "prop":
        eolfix.set_mode_prop()
    elif options.mode == "regexp":
        eolfix.set_mode_regexp( options.regexp )
    if options.eolstyle != None:
        eolfix.set_eol_style( options.eolstyle )
    eolfix.set_fix_options( options.fix )
    if options.fixrevpath != None:
        for f in options.fixrevpath:
            eolfix.set_fix_for_rev_file( f )
    if options.tmpdir != None:
        eolfix.set_temp_dir( options.tmpdir )
    if options.warnfile != None:
        eolfix.set_warning_file( options.warnfile )

    eolfix.execute()
    return 0
        


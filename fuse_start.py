#!/usr/bin/env python

from __future__ import with_statement

import os
import sys
import errno
import sqlite3

from collections import defaultdict
from pprint import pprint

from hachoir_metadata import metadata
from hachoir_core.cmd_line import unicodeFilename
from hachoir_parser import createParser
from fuse import FUSE, FuseOSError, Operations
from stat import *
from os.path import abspath, join
import thread
import ntpath

import shutil
import subprocess
import nltk
import nltk.corpus  
from collections import Counter
from string import punctuation
import docx2txt
from results import ResultsFS
from database import Database
from graph import Graph
import string
import enchant
from nltk.stem.snowball import SnowballStemmer

class MiscFunctions:

    def __init__(self):
        with open('config.json') as config_file:
            self.config = json.load(config_file)

    @classmethod
    def getDirectoryFiles(cls, path):
        '''recursively descend the directory tree rooted at path,
        return list of files under path'''

        if S_ISREG(os.stat(path)[ST_MODE]):
            #print path + " is regular file"
            return [path]

        files = []

        for sub_path in os.listdir(path):
            pathname = os.path.join(path, sub_path)
            mode = os.stat(pathname)[ST_MODE]
            if S_ISDIR(mode):
                # It's a directory, recurse into it
             #   print path + " is directory file"
                files += cls.getDirectoryFiles(pathname)
            elif S_ISREG(mode):
              #  print path + " is regular file"
                # It's a file, call the callback function
                files.append(pathname)
        return files

    @classmethod
    def FileExists(cls, file_name):
        if os.path.exists(file_name): 
            return True
        else:
            return False

    @classmethod 
    def getRelatedTags(cls, tag_name, db_conn):
        tag_name = tag_name.lower()
        tag_id = MiscFunctions.getTagID(tag_name, db_conn)
        if(tag_id == -1):
            print "Tag not found"
            return []
        else:
            graph    = Graph()
            edgelist = db_conn.execute("SELECT * FROM TAGREL").fetchall()
            nodes    = db_conn.execute("SELECT ID FROM TAGS").fetchall()
            nodes    = [x[0] for x in nodes]
            graph.initialize(edgelist, nodes)
            tags     = graph.get_vertices(tag_id)
        
        return tags

    
    @classmethod 
    def storeTagRelInDB(cls,tag1,tag2,db_conn):
        tag1 = tag1.lower()
        tag2 = tag2.lower()
        tag_id1 = MiscFunctions.getTagID(tag1, db_conn)
        tag_id2 = MiscFunctions.getTagID(tag2, db_conn)
        
        print tag_id1, tag_id2
        if(tag_id1 == -1 or tag_id2 == -1):
            print "Either of the tag names do not exist"
            return

        graph    = Graph()
        edgelist = db_conn.execute("SELECT * FROM TAGREL").fetchall()
        nodes    = db_conn.execute("SELECT ID FROM TAGS").fetchall()
        nodes    = [x[0] for x in nodes]
        graph.initialize(edgelist, nodes)
        if graph.checkCycle((tag_id1, tag_id2)):
            print "Can not create relationship. Tags creates cycle"
        else:
            try:
                params = (tag_id1, tag_id2)
                db_conn.execute("INSERT INTO TAGREL (SRC_TAGID, DEST_TAGID) VALUES (?, ?)", params);
                db_conn.commit()
            except sqlite3.IntegrityError:
                print "Relationship already exists"
                
    @classmethod
    def removeTagRelInDB(cls, tag1, tag2, db_conn):
        tag1 = tag1.lower()
        tag2 = tag2.lower()
        tag_id1 = MiscFunctions.getTagID(tag1,  db_conn)
        tag_id2 = MiscFunctions.getTagID(tag2,  db_conn)
        print tag_id1, tag_id2
        if(tag_id1 == -1 or tag_id2 == -1):
            print "Either of the tag names do not exist"
            return
        try:
            params = (tag_id1, tag_id2)
            db_conn.execute("DELETE FROM TAGREL WHERE SRC_TAGID = ? AND DEST_TAGID = ? ", params);
            db_conn.commit()
        except sqlite3.IntegrityError:
            print "Something Bad Happened"
        

    @classmethod
    def getTagID(cls, tag_name, db_conn):
        tag_name = tag_name.lower()
        ret = db_conn.execute("SELECT ID FROM TAGS WHERE NAME = ?", [tag_name]).fetchone()
        y = -1
        if(ret is not None):
            y = ret[0]
        return y

    @classmethod
    def storeTagInDB(cls, file_name, tag_name, db_conn, is_system_tag=0):
        tag_name = tag_name.lower()
        file_name = file_name.lower()
        tag_id = MiscFunctions.getTagID(tag_name, db_conn)
        if(tag_id==-1):
            db_conn.execute("INSERT INTO TAGS (NAME) VALUES (?)", [tag_name])
        tag_id = MiscFunctions.getTagID(tag_name, db_conn)
        params = (file_name, tag_id, is_system_tag)
        try:
            db_conn.execute("INSERT INTO FILES (PATH, TAGID, SYSTEM_TAG) VALUES (?,?,?)", params);
            db_conn.commit()
        except sqlite3.IntegrityError as e:
            print e
        
    @classmethod
    def removeTagInDB(cls, file_name, tag_name, db_conn):
        tag_name = tag_name.lower()
        file_name = file_name.lower()
        tag_id = MiscFunctions.getTagID(tag_name, db_conn)
        if(tag_id==-1):
            print "Tag not present"
        else:
            params = (file_name, tag_id)
            
            try:
                db_conn.execute("DELETE FROM FILES WHERE PATH = ? AND TAGID = ?", params);
                db_conn.commit()
                z = db_conn.execute("SELECT PATH FROM FILES WHERE TAGID = %s" % tag_id);
                db_conn.commit()
                t = z.fetchall()
                if(len(t)==0):

                    db_conn.execute("DELETE FROM TAGS WHERE ID = %s" % tag_id)
                    db_conn.commit()


            except sqlite3.IntegrityError:
                pass

    @classmethod
    def getInode(cls, file_path):
        stat = os.stat(file_path);
        return stat[ST_INO]

    @classmethod
    def removeFromDB(cls, file_name, db_conn):
        file_name = file_name.lower()
        try:
            y = db_conn.execute("SELECT TAGID FROM FILES WHERE PATH='%s'" % file_name);
            db_conn.execute("DELETE FROM FILES WHERE PATH='%s'" % file_name)
            deleted_tagids = [x[0] for x in y.fetchall()]
            print deleted_tagids

            for tag in deleted_tagids:
                z = db_conn.execute("SELECT PATH FROM FILES WHERE TAGID = %s" % tag);
                t =  z.fetchall()
                if(len(t)==0):
                    db_conn.execute("DELETE FROM TAGS WHERE ID = %s" % tag)


            db_conn.commit()
        except sqlite3.IntegrityError:
            pass

    @classmethod
    def update_path_rename(cls, old_file_name, new_file_name, db_conn):
        try:
            db_conn.execute("UPDATE FILES SET PATH = ? WHERE PATH = ?", (new_file_name, old_file_name))
            db_conn.commit()
        except sqlite3.IntegrityError:
            pass

    @classmethod
    def renameFile(cls, old_name, new_name, db_conn):
        old_name = old_name.lower()
        new_name = new_name.lower()
        try:
            db_conn.execute("UPDATE FILES SET PATH = ? WHERE PATH = ?", (new_name, old_name))
            db_conn.commit()
        except sqlite3.IntegrityError:
            pass


    @classmethod
    def getNFrequentWords(cls, nltkObj, n):
        stopwords = set(nltk.corpus.stopwords.words('english'))
        with_stp = Counter()
        without_stp  = Counter()
        dictionary = enchant.Dict("en_US")
        stemmer = SnowballStemmer("english")
        try:
            exclude_set = set(string.punctuation)
            for word in nltkObj:
                # update count off all words in the line that are in stopwords
                word = word.lower()
                word = word.decode("utf-8")
                if word not in stopwords and word not in exclude_set:
                # update count off all words in the line that are not in stopwords
                    if dictionary.check(word):
                        word = stemmer.stem(word)
                        without_stp.update([word])
        except Exception as e:
            pass
        # return a list with top ten most common words from each
        return [y for y,_ in without_stp.most_common(n)]

    @classmethod
    def handleTextFiles(cls, file_path):

        file_path = file_path.lower()
        filename, file_extension = os.path.splitext(file_path)
        getFreqWords = True
        if (file_extension == ".txt"):
            with open(file_path) as inp:
                text = inp.read().split()
        elif (file_extension in [".docx", ".doc"]):
            text = docx2txt.process(file_path).split()
            text = [word.encode("utf-8") for word in text]
            if len(text) == 0:
                getFreqWords = False
        if getFreqWords:
            return MiscFunctions.getNFrequentWords(text, 3)
        else:
            return []

    @classmethod
    def parse_metadata(cls, full_path, db_conn):
        file_ext = os.path.splitext(full_path)[1][1:].lower()
        if(file_ext in ['mp3','bzip2','gzip','zip','tar','wav','midi','bmp','gif','jpeg','jpg','png','tiff','exe','wmv','mkv','mov']):
            # full_path = self._full_path(orig_path)
            # print(full_path)
            parser = createParser(full_path)
            metalist = metadata.extractMetadata(parser).exportPlaintext()
            for item in metalist:
                x = item.split(':')[0] 
                if item.split(':')[0][2:].lower() in ["author","album","music genre"]:
                    # print(item.split(':')[1][1:])
                    item1 = item.split(':')[1][1:]
                    new_item = str(item1.decode('utf-8'))
                    print new_item
                    new_item = string.replace(new_item, ";", ",")
                    new_item = string.replace(new_item, "|", ",")
                    tag_name = new_item.split(',')
                    print(tag_name)
                    for names in tag_name:
                        # inode = os.stat(full_path)[ST_INO
                        tagname = names.strip()
                        MiscFunctions.storeTagInDB(full_path, tagname, db_conn, is_system_tag=1)

            print("Database storage successful")
        elif file_ext in ["docx", "doc", "txt"]:
            tags = MiscFunctions.handleTextFiles(full_path)
            for tagname in tags:
                print "txt file tag: %s" % tagname
                MiscFunctions.storeTagInDB(full_path, tagname, db_conn, is_system_tag=1)

    @classmethod
    def update_system_tags(cls, file_path, db_conn):
        cursor = db_conn.execute("DELETE from FILES WHERE SYSTEM_TAG = ? AND PATH=?", ("1", file_path))
        db_conn.commit()
        cls.parse_metadata(file_path, db_conn)


class Passthrough(Operations):
    def __init__(self, root):
        self.db_conn = Database().initialize()
        self.root = root
        print(root)
        self.initialize(root)

    # Helpers
    # =======
    def add_tag(self, path, buf):
        orig_path = path
        ##print "buffer is %s" % buf
        for command in buf.splitlines():
            contents = command.split(" ")
            print "contents is %s" % contents
            operation = contents[0]
            contents = (" ".join(contents[1:])).split("=")
            if len(contents) == 1:
                path = self._full_path(orig_path)[:-4]
                tag_name = contents[0]
                if os.path.exists(path):
                    files = MiscFunctions.getDirectoryFiles(path)
                    for filename in files:
                        if(operation == 'add'):
                            if MiscFunctions.FileExists(filename):
                                MiscFunctions.storeTagInDB(filename, tag_name, self.db_conn)
                        elif(operation == 'remove'):
                            if MiscFunctions.FileExists(filename):
                                MiscFunctions.removeTagInDB(filename, tag_name, self.db_conn)
                        else:
                            print "Wrong operation - tag [add|remove] filename tagname"
                else:
                    print "Path does not exist"
            elif len(contents) == 2:
                file_name = contents[0]
                tag_name = contents[1]
                file_path = self._full_path(orig_path[:-4] + file_name)
                if(operation == 'add'):
                    if MiscFunctions.FileExists(file_path):
                        MiscFunctions.storeTagInDB(file_path, tag_name, self.db_conn)
                    else:
                        print "File does not exist"
                else:
                    if MiscFunctions.FileExists(file_path):
                        MiscFunctions.removeTagInDB(file_path, tag_name, self.db_conn)
                    else:
                        print "File does not exist"
            
    # Helpers
    # =======
    def initialize(self, root):
        for sub_path in MiscFunctions.getDirectoryFiles(root):
            print sub_path
            mode = os.stat(sub_path)[ST_MODE]
            if(S_ISREG(mode)):
                MiscFunctions.parse_metadata(sub_path.decode('utf-8'), self.db_conn)
                

    def ls_tags(self, path, buf):
        orig_path = path
        for command in buf.splitlines():
            contents = command.split(" ")
            print "contents is %s" % contents
            if(contents[0]=='-f' or contents[0] == ''):

                contents = contents[1:]
                data = " ".join(contents)
                print data
                if contents == []:
                    path = ''
                elif data.strip() == "":
                    index = orig_path.index(".")
                    path = self._full_path(orig_path)[:index]
                else:
                    path = self._full_path(data)
                cursor = self.db_conn.execute("SELECT f.PATH, t.NAME FROM FILES f, TAGS t WHERE f.TAGID = t.ID AND f.PATH like ?", [path+'%'])
                result = dict()

                for row in cursor:
                    if row[0] not in result:
                        result[row[0]] = []
                    result[row[0]] += [row[1]]
                if(len(result) == 0):
                    print "No results found."
                for item in result:
                    print item
                    print ",".join(result[item])
                    print "--------------------------------------------------"
                print "\n\n===============================================================================================\n"
            elif(contents[0]=='-t'):
                contents = contents[1:]
                related_tagids = MiscFunctions.getRelatedTags(" ".join(contents), self.db_conn)
                query = "SELECT NAME FROM TAGS WHERE ID IN (%s) AND NAME != ?" % ','.join('?'*len(related_tagids))
                cursor = self.db_conn.execute(query, related_tagids+[contents[0]])
                related_tags = [x[0] for x in cursor.fetchall()]
                
                print "Tag:", " ".join(contents)
                print "Related to:"
                print ",".join(related_tags)
                print "\n\n===============================================================================================\n"
            

    #Helper to fill data in results
    def fill_results(self, path, contents):
        if contents[0].strip() == "":
            index = orig_path.index(".")
            path = self._full_path(orig_path)[:index]
        else:
            path = self._full_path(contents[0])
        query = "SELECT f.PATH FROM FILES f, TAGS t WHERE f.TAGID = t.ID AND t.NAME IN (%s)" % ','.join('?'*len(contents))
        cursor = self.db_conn.execute(query, contents)
        result = set()
        for row in cursor:
            result.add(row[0])
        result = list(result)
        result_path = "results/"
        full_result_path = self._full_path(result_path)
        print(os.listdir(full_result_path))

        for path in os.listdir(full_result_path):
            try:
                os.unlink(self._full_path(result_path+path))
            except:
                pass
        os.rmdir(full_result_path)
        os.mkdir(full_result_path)

    # Generate hard links for the files in the results directory
        print(result)
        for filepath in result:
            self.create_links(filepath, result_path)
            # partial = filepath.split('/')[-1]
            # path = self._full_path(partial)
            # os.symlink(filepath, path)

    def create_links(self, filepath, result_path):
        new_path = os.path.basename(filepath)
        new_full_path = self._full_path(result_path+new_path)
        print(filepath)
        print(new_full_path)
        os.symlink(filepath, new_full_path)

    #Use getfiles tagname to list all files in results on mountpoint
    def get_files(self, path, buf):
        # orig_path = path
        # for command in buf.splitlines():
        #     contents = command.split(" ")
        #     print orig_path
        #     self.fill_results(orig_path, contents)
        orig_path = path

        #print "buffer is %s" % buf
        for command in buf.splitlines():
            contents  = command.split(",")
            print contents
            related_tags = [MiscFunctions.getRelatedTags(x.strip(), self.db_conn) for x in contents]
            print related_tags
            search_tags = set()
            for tags in related_tags:
                search_tags = search_tags.union(set(tags))
            print search_tags
            
            query = "SELECT f.PATH FROM FILES f, TAGS t WHERE f.TAGID = t.ID AND t.ID IN (%s)" % ','.join('?'*len(search_tags))

            cursor = self.db_conn.execute(query, map(str, search_tags))
            result = set()
            for row in cursor:
                result.add(row[0])
            result = list(result)

            print "Result is: ", result 
            result_path = "/Users/Rahul/Desktop/results/"

            for x in result:
                print x 
            print "Result is in", result_path

            for path in os.listdir(result_path):
                try:        
                    os.unlink(os.path.join(result_path, path))
                except:
                    pass

        # Generate hard links for the files in the results directory
            for filepath in result:
                try:
                    partial = filepath.split('/')[-1]
                    path = os.path.join(result_path, partial)
                    os.symlink(filepath, path)
                except:
                    pass

    def remove_tags(self, path, buf):
        orig_path = path
        print "Removing Tag %s" %buf
        for command in buf.splitlines():
            contents = command.strip()
            tag_name = contents
            try:
                query = "DELETE FROM TAGS WHERE NAME = (?)"
                self.db_conn.execute("PRAGMA FOREIGN_KEYS = ON")
                self.db_conn.execute(query, [tag_name]);
            except sqlite3.IntegrityError:
                pass
            self.db_conn.commit()
            # self.db_conn.execute(query, [tag_name])

    def bool_exp(self, path, buf):
        print buf
        result = set()
        if(buf.find("AND")):
            contents = buf.strip().split("AND")
            if (len(contents)==2):
                tag1 = contents[0].strip()
                tag2 = contents[1].strip()
                print(tag1 + "asdfasdf" + tag2)
                if(tag1 is "" or tag2 is ""):
                    print ("One of the tags is empty")
                else:
                    query = "SELECT F.PATH FROM FILES F, TAGS T WHERE F.TAGID = T.ID AND T.NAME = ?  \
                        INTERSECT SELECT F1.PATH FROM FILES F1, TAGS T1 WHERE F1.TAGID = T1.ID AND T1.NAME = ?"
                    # print(query)
                    cursor = self.db_conn.execute(query, (tag1, tag2))
                    for row in cursor:
                        result.add(row[0])
            else:
                print "Please add only two tags"
        if(buf.find("OR")):
            contents = buf.strip().split("OR")
            print(contents)
            if (len(contents)==2):
                tag1 = contents[0].strip()
                tag2 = contents[1].strip()
                print(tag1 + "asdfasdf" + tag2)
                if(tag1 is "" or tag2 is ""):
                    print ("One of the tags is empty")
                else:
                    query = "SELECT F.PATH FROM FILES F, TAGS T WHERE F.TAGID = T.ID AND T.NAME = ?  \
                        UNION SELECT F1.PATH FROM FILES F1, TAGS T1 WHERE F1.TAGID = T1.ID AND T1.NAME = ?"
                    # print(query)
                    cursor = self.db_conn.execute(query, (tag1, tag2))
                    for row in cursor:
                        result.add(row[0])
            else:
                print "Please add only two tags"        
        print(result)
        result = list(result)
        result_path = "results/"
        full_result_path = self._full_path(result_path)
        print(os.listdir(full_result_path))

        for path in os.listdir(full_result_path):
            try:
                os.unlink(self._full_path(result_path+path))
            except:
                pass
        os.rmdir(full_result_path)
        os.mkdir(full_result_path)

    # Generate hard links for the files in the results directory
        print(result)
        for filepath in result:
            self.create_links(filepath, result_path)                


    def rel_tags(self, path, buf):
        orig_path = path
        print path
        #print "buffer is %s" % buf
        for command in buf.splitlines():

            contents = command.strip().split(" ")
            print "contents is %s" % contents
            operation = contents[0]
            contents = (" ".join(contents[1:])).split(">")
            if len(contents)==1:
                print "Please add two tags"
            else:
                tag1 = contents[0].strip()
                tag2 = contents[1].strip()
                if(tag1 is "" or tag2 is ""):
                    print("One of the tags is empty")
                else:
                    if(operation == "add"):
                        MiscFunctions.storeTagRelInDB(tag1, tag2, self.db_conn)
                    elif(operation == "remove"):
                        MiscFunctions.removeTagRelInDB(tag1, tag2, self.db_conn)
                    else:
                        print "Wrong operation"

    def _full_path(self, partial):
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path

    # Filesystem methods
    # ==================

    def access(self, path, mode):
        # print(path)
        full_path = self._full_path(path)
        if not os.access(full_path, mode):
            raise FuseOSError(errno.EACCES)

    def chmod(self, path, mode):
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)

    def chown(self, path, uid, gid):
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)

    def getattr(self, path, fh=None):
        full_path = self._full_path(path)
        st = os.lstat(full_path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                     'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def readdir(self, path, fh):
        full_path = self._full_path(path)
        dirents = ['.', '..']
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))
        for r in dirents:
            yield r

    def readlink(self, path):
        pathname = os.readlink(self._full_path(path))
        if pathname.startswith("/"):
            # Path name is absolute, sanitize it.
            return os.path.relpath(pathname, self.root)
        else:
            return pathname

    def mknod(self, path, mode, dev):
        return os.mknod(self._full_path(path), mode, dev)

    def rmdir(self, path):
        full_path = self._full_path(path)
        return os.rmdir(full_path)

    def mkdir(self, path, mode):
            return os.mkdir(self._full_path(path), mode)

    def statfs(self, path):
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def unlink(self, path):
        #print path
        full_path = self._full_path(path)
        file_name = os.path.basename(path)
        
        files = MiscFunctions.getDirectoryFiles(full_path)
        for file in files:
            print file
            if not (ntpath.basename(file) in ['.tag', '.ls', '.gf', '.graph']):
                MiscFunctions.removeFromDB(file, self.db_conn)

        return os.unlink(self._full_path(path))

    def symlink(self, name, target):
        return os.symlink(name, self._full_path(target))

    def rename(self, old, new):
        full_old_path = self._full_path(old)
        full_new_path = self._full_path(new)
        mode = os.stat(full_old_path)[ST_MODE]
        if S_ISDIR(mode):
            print "IN here"
            for sub_path in MiscFunctions.getDirectoryFiles(full_old_path):
                print sub_path
                new_path = os.path.join(self._full_path(new)+'/'+os.path.basename(sub_path))
                MiscFunctions.update_path_rename(sub_path, new_path, self.db_conn)

        elif S_ISREG(mode):
            print "In here"
            MiscFunctions.renameFile(full_old_path, full_new_path, self.db_conn)
        # full_old_path = self._full_path(old)
        # print full_old_path
        # full_new_path = self._full_path(new)
        # print full_new_path
        # MiscFunctions.renameFile(full_old_path, full_new_path, self.db_conn)
        return os.rename(self._full_path(old), self._full_path(new))

    def link(self, target, name):
        return os.link(self._full_path(target), self._full_path(name))

    def utimens(self, path, times=None):
        return os.utime(self._full_path(path), times)

    # File methods
    # ============

    def open(self, path, flags):
        full_path = self._full_path(path)
        return os.open(full_path, flags)

    def create(self, path, mode, fi=None):
        full_path = self._full_path(path)
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    def read(self, path, length, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        file_name = ntpath.basename(path);
        name, file_extension = os.path.splitext(path)
        if file_name == ".tag":
            self.add_tag(path, buf)
        elif file_name == ".ls":
            self.ls_tags(path, buf)
        elif file_name == ".gf":
            self.get_files(path, buf)
        elif file_name == ".graph":
            self.rel_tags(path, buf)
        elif file_name == ".tagr":
            self.remove_tags(path, buf)
        elif file_name == ".searchq":
            if(buf.find("AND") or buf.find("OR")):
                self.bool_exp(path, buf)
            else:
                print("Unsupported query. Please make necessary changes.")
        elif file_extension in [".txt", ".doc", ".docx"]:
            MiscFunctions.update_system_tags(self._full_path(path), self.db_conn)
        if(file_name in [".tag", ".ls", ".gf", ".graph", ".tagr", ".searchq"]):
            os.unlink(self._full_path(path))
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, buf)

    def truncate(self, path, length, fh=None):
        full_path = self._full_path(path)
        with open(full_path, 'r+') as f:
            f.truncate(length)

    def flush(self, path, fh):
        return os.fsync(fh)

    def release(self, path, fh):
        full_path = self._full_path(path)
        MiscFunctions.parse_metadata(full_path, self.db_conn)
        return os.close(fh)

    def fsync(self, path, fdatasync, fh):
        return self.flush(path,fh)

def main(mountpoint, root):
    FUSE(Passthrough(root), mountpoint, nothreads=True, foreground=True)

if __name__ == '__main__':
    main(sys.argv[2], sys.argv[1])

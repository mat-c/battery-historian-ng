#! /bin/sh

#parse all file from cmdline

set -e

for file in $@
do
        bname=$(basename $file)
        ../extract_from_br.sh $file > /tmp/$bname.bat
        ../parse.py < /tmp/$bname.bat > /tmp/$bname.bat.json
done

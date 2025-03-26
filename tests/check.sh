set -e

cd $(dirname $0)
mkdir -p out

for file in *.txt
do
        trap "echo $file.json" EXIT
        echo $file
        cat $file | ../parse.py  > out/$file.json
        diff -u $file.json out/$file.json
done

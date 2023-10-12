#!/bin/bash
filename='repos.txt'

while read line; do
# reading each line

git clone $line

done < $filename 

echo 'finished'

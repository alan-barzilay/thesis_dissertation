#!/bin/bash
search_dir="cloned_repos"

function mine_repo(){
  repo=$1
  repo=$(basename "$repo")
  if [[ ! -f "./jsons/$repo.json" ]]; then  
    echo "mining $repo" 
    ./RefactoringMiner-2.1.0/bin/RefactoringMiner -a ./repos_clonados/$repo -json ./jsons/$repo.json
  fi
}
export -f mine_repo


echo "Starting mining"
ls $search_dir | parallel mine_repo
echo "Everything mined - the end - acabou - finito"
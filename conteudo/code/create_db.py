data_path="./jsons/"
import json
import subprocess
import glob
import pandas as pd

from tqdm.asyncio import tqdm
from asyncio import run
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import Column, Integer, Text, String, Boolean

import logging

logger = logging.getLogger("processing_jsons")
logger.setLevel(logging.DEBUG)
f_handler = logging.FileHandler('processing_jsons.log')
f_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
logger.addHandler(f_handler)

def process_json(json_name):

    results = []
    with open(f"{data_path}{json_name}", "r") as read_file:
        try:
            json_payload = json.load(read_file)
        except json.JSONDecodeError as e:
            logger.debug(f"Broken json - {json_name}")
            return

        if not json_payload["commits"]:  #if is empty
            logger.debug(f"Empty json - {json_name}")
            return

        repository = json_payload["commits"][0]['repository']

        for commit in json_payload["commits"]:
            for refactoring in commit["refactorings"]:
                if refactoring["type"] == "Extract Method":
                    refactored_function = refactoring["leftSideLocations"][0]
                    start = refactored_function['startLine']
                    end = refactored_function['endLine']

                    extracted_lines = get_lines(
                        refactoring["leftSideLocations"])

                    #if for some reason the extracted lines are not being encompassed by the function,
                    #skip this refactoring
                    if not all([start <= i <= end for i in extracted_lines]):
                        logger.debug(f"extracted lines are not being encompassed by the function - {json_name}")
                        continue

                    #if the body returns the empty string, lets skip this refactoring
                    #because we had a decoding error
                    if not (refactored_function_body := get_function_body(
                            start, end, repository, commit['sha1'],
                            refactored_function['filePath'])):
                        continue

                    continuous_refac = check_continuous(
                        start, extracted_lines, refactored_function_body)

                    results.append({
                        'repository':
                        repository,
                        'sha1':
                        commit['sha1'],
                        'url':
                        commit['url'],
                        #transform into string to insert it in the sqlite db
                        "extracted_lines":
                        str(extracted_lines),
                        "shifted_extracted_lines":
                        str([i - start for i in extracted_lines]),
                        'refactoring_description':
                        refactoring['description'],
                        'file_path':
                        refactored_function['filePath'],
                        'func_startline':
                        start,
                        'func_endline':
                        end,
                        "shifted_extracted_lines_start":
                        extracted_lines[0]-start,
                        "shifted_extracted_lines_end":
                        extracted_lines[-1]-start,
                        'refactored_function_body':
                        refactored_function_body,
                        'continuous':
                        continuous_refac
                    })
    return results


def get_lines(elements):
    """
    gets the specific line numbers of the lines extracted in the refactoring and return them as a sorted list.
    """
    lines = set()
    for element in elements[1:]:
        if element['startLine'] == element['endLine']:
            lines.add(element['startLine'])
        else:
            lines.update(range(element['startLine'], element['endLine'] + 1))

    lines_list = list(lines)
    lines_list.sort()
    return lines_list


def get_function_body(start,
                      end,
                      repo,
                      commit_hash,
                      file_path,
                      path_gits="/disk1/barzilay/repos_clonados"):
    """
    use git to get the file and then extract only the function body
    """
    repo = repo.split("/")[-1]
    cmd = subprocess.run(["git", "show", f"{commit_hash}^:{file_path}"],
                         cwd=f"{path_gits}/{repo}",
                         capture_output=True)

    try:
        file_contents = cmd.stdout.decode("utf-8")
    except UnicodeDecodeError as e:
        logger.error(f"Decoding error at repo: {repo}", exc_info=True)
        return ""
    # java parser counts lines starting from 1 but python lists start at 0
    body = "\n".join(file_contents.split("\n")[start - 1:end])
    return body


def check_continuous(start, lines, body):
    """
    check if the function extraction was continuous or if it is composed of multiple line spans. Comments and blank lines are treated as part of refactorings, i.e. if the lines of code being extracted are continuous with the exception of comments in the middle of said lines, the refactoring will be considered continuous.
    """
    interval = {i for i in range(lines[0], lines[-1] + 1)}
    difference = interval - set(lines)
    to_check = [i - start for i in difference]
    to_check.sort()

    body_lines = body.split("\n")
    long_comment = False

    for index in to_check:
        line = body_lines[index].strip()

        #if whitespace or comment
        if not line or line[0:2] == "//":
            continue

        elif line[0:2] == "/*" or long_comment == True:
            long_comment = True
            #check if the long comment ended in this line and if there is any code after it
            end_long_comment = line.find("*/")
            if end_long_comment != -1:
                if end_long_comment + 2 != len(line): return False
                long_comment = False
        else:
            return False

    return True



Base = declarative_base()


class Refactoring(Base):
    """
    Refactoring class used for the ORM between our code base in SQLite and our python objects obtained after processing the JSON files.

    This class and its methods were developed with Rafael S. Durelli.
    """
    __tablename__ = 'refactoring'
    id = Column(Integer, primary_key=True)
    repository = Column(String(1000))
    sha1 = Column(String(43))
    url = Column(String(1000))
    extracted_lines = Column(String(10000))
    shifted_extracted_lines= Column(String(10000))
    refactoring_description = Column(String(3000))
    file_path = Column(String(1000))
    func_startline = Column(Integer)
    func_endline = Column(Integer)
    continuous = Column(Boolean)
    refactored_function_body = Column(Text())
    shifted_extracted_lines_start= Column(Integer)
    shifted_extracted_lines_end= Column(Integer)

    
    

    def __repr__(self):
        return f'<Refactoring> {self.id} {self.repository} {self.sha1} {self.url} {self.extracted_lines} {self.refactoring_description} {self.file_path} {self.func_startline} {self.func_endline} {self.refactored_function_body} '

    @staticmethod
    async def insert_refactoring_list(session, refactoring_list):
        """
        static method used to add a list of Refactoring python objects into the SQLite database in an asynchronous fashion.
        """
        async with session() as s:
            s.add_all([
                Refactoring(**refactoring_to_insert)
                for refactoring_to_insert in refactoring_list
            ])
            await s.commit()


db_url = 'sqlite+aiosqlite:///refactorings.db'
engine = create_async_engine(db_url)

session = sessionmaker(engine,
                       expire_on_commit=False,
                       future=True,
                       class_=AsyncSession)


async def create_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)



run(create_database())

jsons_list= glob.glob("*.json", root_dir=data_path)

with tqdm(jsons_list) as pbar:
    async for json_file in pbar:
        mined_refactorings=process_json(json_file)
        if mined_refactorings:
            await Refactoring.insert_refactoring_list(session, mined_refactorings)


from __future__ import print_function
import argparse
import pickle
import os
import sys
import gzip
import tempfile
import pandas as pd
from itertools import izip
from flask import Flask, request, send_file
from rdkit import Chem
from rdkit.Chem import inchi
from chemfp.commandline import rdkit2fps
from chemfp.commandline import simsearch

identifier_mol_mapping = {"smiles": Chem.MolFromSmiles, "inchi": inchi.MolFromInchi}

app = Flask(__name__)


@app.route("/fingerprints/fingerprint_db", methods=["POST"])
def fingerprint_db():
    cmpd_json = request.json["compounds"]
    cmpd_encoding = request.json["request"]["encoding"]
    input_df = pd.DataFrame(cmpd_json)
    print (input_df.head())
    mol_func = identifier_mol_mapping[cmpd_encoding]
    temp_sdf = tempfile.NamedTemporaryFile(mode="wb", suffix=".sdf.gz", delete=False)
    temp_sdf_gz = gzip.GzipFile(fileobj=temp_sdf)
    sdf_writer = Chem.SDWriter(temp_sdf_gz)
    for cmpd in input_df.itertuples():
        m = mol_func(str(cmpd.compound))
        m.SetProp("name", str(cmpd.name))
        sdf_writer.write(m)
    sdf_writer.close()
    temp_sdf_gz.close()
    temp_sdf.close()
    print ("Wrote molecules to sdf", temp_sdf.name)
    temp_fps = tempfile.mkstemp(suffix=".fps")
    rdkit2fps.main(["-o", temp_fps[1], "--id-tag", "name", temp_sdf.name])
    os.remove(temp_sdf.name)
    return send_file(temp_fps[1])


def pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)


def parse_sim_result(sim_result_file):
    res = list()
    with open(sim_result_file, "r") as f:
        for line in f:
            if line.startswith("#"):
                continue
            l = line.split()
            if len(l) <= 2:
                continue
            query = l[1]
            for match, score in pairwise(l[2:]):
                res.append((query, match, score))
    return zip(*res)


@app.route("/fingerprints/simsearch", methods=["POST"])
def fingerprint_search():
    fingerprint_db = request.files.get("fingerprint_db", None)
    if not fingerprint_db:
        raise ValueError("No fingerprint db supplied")
    fingerprint_query = request.files.get("fingerprint_query", None)
    threshold = request.form.get("threshold", 0.9)
    temp_db = tempfile.mkstemp(suffix=".fps")
    temp_out = tempfile.mkstemp(suffix=".txt")
    fingerprint_db.save(temp_db[1])
    args = []
    if fingerprint_query:
        temp_query = tempfile.mkstemp(suffix=".fps")
        fingerprint_query.save(temp_query[1])
        args.extend(["-q", temp_query[1]])
    else:
        args.append("--NxN")
    simsearch.main(args + ["-o", temp_out[1], "-t", str(threshold), temp_db[1]])
    sim_results = parse_sim_result(temp_out[1])
    return {"query": sim_results[0], "match": sim_results[1], "score": sim_results[2]}
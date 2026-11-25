"""Cold ZIP-only preflight. Not MaiBot Host/Runner acceptance. No account used."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def check(archive,host):
    archive=archive.resolve(); host=host.resolve(); env=dict(os.environ,PYTHONUTF8='1',PYTHONNOUSERSITE='1'); env.pop('PYTHONPATH',None)
    with tempfile.TemporaryDirectory(prefix='siwc-cold-') as tmp:
        root=Path(tmp); plugin=root/'maibot_chatgpt_provider_plugin'; v=root/'env'; py=v/('Scripts/python.exe' if os.name=='nt' else 'bin/python'); private=root/'private'
        with zipfile.ZipFile(archive) as z:
            assert all(p.startswith(plugin.name+'/') and '..' not in Path(p).parts for p in z.namelist()); assert z.testzip() is None; z.extractall(root); print('CRC and isolated unpack OK:',len(z.namelist()),'files',flush=True)
        def run(*cmd,cwd=plugin,quiet=False): subprocess.run(cmd,cwd=cwd,env=env,check=True,stdout=subprocess.DEVNULL if quiet else None)
        run('uv','venv','--python',sys.executable,str(v)); run('uv','pip','install','--python',str(py),'-r','requirements.txt'); run('uv','pip','check','--python',str(py)); run(str(py),'scripts/login.py','--help',quiet=True)
        run(str(py),'scripts/login.py','--data-dir',str(private),'init-host',quiet=True); run(str(py),'scripts/login.py','--data-dir',str(private),'status','--json'); run(str(py),'scripts/login.py','--data-dir',str(private),'doctor')
        run(str(py),'-c',"import importlib.util as u,sys;s=u.spec_from_file_location('cold_plugin','plugin.py',submodule_search_locations=['.']);m=u.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);p=m.create_plugin();assert [v['client_type'] for v in p.get_llm_providers()]==['maibot.chatgpt.subscription'];print('isolated SDK factory OK')")
        run(str(py),'scripts/package_plugin.py','--preview','--output-dir',str(root/'rebuild')); rebuilt=root/'rebuild'/archive.name; assert hashlib.sha256(archive.read_bytes()).digest()==hashlib.sha256(rebuilt.read_bytes()).digest(); print('byte-identical rebuild OK',flush=True)
        # Validator is the actual checkout using the probe interpreter, NOT an artificial validator or cold venv dependency.
        run(sys.executable,'-c',"import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from src.plugin_runtime.runner.manifest_validator import PluginManifest;from pydantic import ValidationError\ntry: PluginManifest.model_validate_json(Path(sys.argv[2]).read_bytes())\nexcept ValidationError as e: assert {x['loc'] for x in e.errors()}=={('author','url'),('urls','repository')};print('cold manifest: expected BLOCKED author.url + urls.repository')\nelse: raise AssertionError('unexpected manifest result')",str(host),str(plugin/'_manifest.json'),cwd=root)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('baseline_host',type=Path);args=p.parse_args();check(args.archive,args.baseline_host)

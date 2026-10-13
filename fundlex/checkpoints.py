"""Task-local model judgments; structure, evidence positions and edits are recomputed."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import jsonschema


class ModelCheckpoints:
    def __init__(self, directory: Path, dependencies: dict):
        self.directory = Path(directory)
        self.dependencies = dependencies
        self.invalidations = 0

    @staticmethod
    def digest(value) -> str:
        return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
            separators=(',',':')).encode()).hexdigest()

    def _path(self, query):
        return self.directory / (self.digest({'dependencies':self.dependencies,'query':query})+'.json')

    def load(self, query, context, schema):
        path = self._path(query)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > 1_000_000:
                raise ValueError('oversize')
            envelope = json.loads(path.read_text(encoding='utf-8'))
            body = envelope['body']
            if not isinstance(body,dict):
                raise ValueError('invalid body')
            if envelope['sha256'] != self.digest(body) or body['dependencies'] != self.dependencies or body['query'] != query:
                raise ValueError('dependency/integrity mismatch')
            value, event = body['value'], body['event']
            if not isinstance(event,dict):
                raise ValueError('invalid event')
            jsonschema.validate(value,schema)
            if event.get('error_code') or event.get('reused_checkpoint') or event.get('http_status') != 200:
                raise ValueError('not a successful original response')
            if not event.get('actual_model') or event['task_type'] != query['task_type'] or event['prompt_version'] != query['prompt_version'] or event['context_sha256'] != query['bounded_context_sha256']:
                raise ValueError('response context mismatch')
            def quotes(obj):
                if isinstance(obj,dict):
                    for key,item in obj.items():
                        if key in {'quote','evidence_quote'} and isinstance(item,str):
                            yield item
                        else:
                            yield from quotes(item)
                elif isinstance(obj,list):
                    for item in obj:
                        yield from quotes(item)
            if any(quote and quote not in context for quote in quotes(value)):
                raise ValueError('quote mismatch')
            return value,event
        except (OSError,ValueError,KeyError,TypeError,jsonschema.ValidationError):
            self.invalidations += 1
            return None

    def save(self, query, value, event):
        self.directory.mkdir(parents=True,exist_ok=True)
        body = {'schema':'model-checkpoint-v1','dependencies':self.dependencies,'query':query,
                'value':value,'event':dict(event)}
        envelope = {'body':body,'sha256':self.digest(body)}
        path = self._path(query)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.directory,
                    prefix='.checkpoint-',suffix='.tmp',delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(envelope,stream,ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

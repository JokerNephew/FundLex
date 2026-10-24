"""Task-local model judgments; structure, evidence positions and edits are recomputed."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import jsonschema


CHECKPOINT_SCHEMA = 'model-checkpoint-v1'


class ModelCheckpoints:
    def __init__(self, directory: Path, dependencies: dict):
        self.directory = Path(directory)
        if not isinstance(dependencies, dict):
            raise TypeError("checkpoint dependencies must be a mapping")
        # Store a detached, canonical value.  A caller must not be able to
        # mutate a live gateway binding after it has started producing cache
        # keys; doing so would make the same directory contain mixed builds.
        # Import lazily to keep this low-level module independent at import time.
        # The build is part of the cache namespace even for legacy callers that
        # only supplied source/engine identifiers.
        from .store import engine_build
        bound = dict(dependencies)
        bound['engine_build'] = engine_build()
        self.dependencies = json.loads(json.dumps(bound, ensure_ascii=False,
                                                   sort_keys=True, separators=(",", ":")))
        self.invalidations = 0

    @staticmethod
    def digest(value) -> str:
        return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
            separators=(',',':')).encode()).hexdigest()

    def _path(self, query):
        return self.directory / (self.digest({'dependencies':self.dependencies,'query':query})+'.json')

    @staticmethod
    def _query_is_bound(query: object) -> bool:
        return (isinstance(query, dict)
                and isinstance(query.get('task_type'), str) and bool(query['task_type'])
                and isinstance(query.get('prompt_version'), str) and bool(query['prompt_version'])
                and isinstance(query.get('bounded_context_sha256'), str)
                and len(query['bounded_context_sha256']) == 64
                and all(char in '0123456789abcdef'
                        for char in query['bounded_context_sha256'].lower()))

    def load(self, query, context, schema):
        if not self._query_is_bound(query):
            self.invalidations += 1
            return None
        if hashlib.sha256(context.encode('utf-8')).hexdigest() != query['bounded_context_sha256']:
            self.invalidations += 1
            return None
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
            if (envelope['schema'] != CHECKPOINT_SCHEMA
                    or envelope['sha256'] != self.digest(body)
                    or body.get('schema') != CHECKPOINT_SCHEMA
                    or body['dependencies'] != self.dependencies
                    or body['query'] != query):
                raise ValueError('dependency/integrity mismatch')
            value, event = body['value'], body['event']
            if not isinstance(event,dict):
                raise ValueError('invalid event')
            jsonschema.validate(value,schema)
            if (event.get('error_code') or event.get('reused_checkpoint')
                    or event.get('http_status') != 200):
                raise ValueError('not a successful original response')
            if (not event.get('actual_model')
                    or event.get('task_type') != query['task_type']
                    or event.get('prompt_version') != query['prompt_version']
                    or event.get('context_sha256') != query['bounded_context_sha256']):
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
        if not self._query_is_bound(query):
            raise ValueError('checkpoint query is not bound to a request')
        if (not isinstance(value, dict) or not isinstance(event, dict)
                or event.get('error_code') or event.get('reused_checkpoint')
                or event.get('http_status') != 200
                or not event.get('actual_model')
                or event.get('task_type') != query['task_type']
                or event.get('prompt_version') != query['prompt_version']
                or event.get('context_sha256') != query['bounded_context_sha256']):
            raise ValueError('only successful bound responses may be checkpointed')
        self.directory.mkdir(parents=True,exist_ok=True)
        body = {'schema':CHECKPOINT_SCHEMA,'dependencies':self.dependencies,'query':query,
                'value':value,'event':dict(event)}
        envelope = {'schema': CHECKPOINT_SCHEMA, 'body':body,'sha256':self.digest(body)}
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

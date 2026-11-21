"""Check pinned supplier adapters and Maa-native top results; never steering.

The eight-class legend model is a crop classifier, not a box detector. The path
model has nine independent sigmoid outputs: native softmax scores are NOT path
probabilities. Full logits are compared through reference/adapter ONNXRuntime;
the current native public result exposes only top class and rounded score.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from maalimbus.replay import ReplayController


def adapter(body):
    """Preserve supplier weights/logits; adapt native RGB/255 to ImageNet input."""
    import numpy as np
    import onnx
    from onnx import helper, numpy_helper
    model = onnx.load_model_from_string(body)
    original = model.graph.input[0].name
    names = {v.name for v in model.graph.input} | {v.name for v in model.graph.initializer}
    names |= {v for node in model.graph.node for v in list(node.input) + list(node.output)}
    prefix = 'maalimbus_native_adapter_'
    if any(name.startswith(prefix) for name in names):
        raise ValueError('Adapter tensor name collision')
    inp = model.graph.input[0]
    inp.name = prefix + 'rgb'
    inp.type.tensor_type.shape.dim[0].ClearField('dim_param')
    inp.type.tensor_type.shape.dim[0].dim_value = 1
    for output in model.graph.output:
        output.type.tensor_type.shape.dim[0].ClearField('dim_param')
        output.type.tensor_type.shape.dim[0].dim_value = 1
    for key, values in [('mean', [.485, .456, .406]), ('std', [.229, .224, .225])]:
        model.graph.initializer.append(numpy_helper.from_array(
            np.asarray(values, np.float32).reshape(1, 3, 1, 1), prefix + key))
    nodes = [helper.make_node('Sub', [inp.name, prefix + 'mean'], [prefix + 'centred']),
             helper.make_node('Div', [prefix + 'centred', prefix + 'std'], [original])]
    old = list(model.graph.node)
    del model.graph.node[:]
    model.graph.node.extend(nodes + old)
    onnx.checker.check_model(model)
    return model.SerializeToString()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.out.resolve().is_relative_to(ROOT / 'build'):
        raise ValueError('Keep the local probe report in build')
    import cv2
    import numpy as np
    import onnxruntime as ort
    from maa.library import Library
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.pipeline import JRecognitionType, JNeuralNetworkClassify
    from maalimbus.jobs import wait_job
    from pinned_lalc import verify_snapshot

    archive = ROOT / 'sources/upstream/LixAssistantLimbusCompany.source.zip'
    manifest_path = archive.with_suffix('.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    revision = '431b432e22f0b0da08b95d7c478fa213be20b3e8'
    verify_snapshot(archive, manifest, revision)
    frame = ROOT / 'evidence/runtime/packaged-mirror-20261117-010749/frame-0092.png'
    image = cv2.imread(str(frame))
    if image is None:
        raise ValueError('Retained real frame required')
    crops = [('red_room', [975, 749, 188, 157]),
             ('path_chevron', [810, 775, 120, 110]),
             ('map_background', [1300, 500, 130, 110])]
    rows = []
    Library.open(ROOT / 'dist/MaaLimbus/maafw', agent_server=False)
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory(prefix='maalimbus-map-nn-parity-') as temp:
        bundle = Path(temp)
        (bundle / 'model/classify').mkdir(parents=True)
        source_provenance = {name: hashlib.sha256(source.read(name)).hexdigest()
                             for name in source.namelist()
                             if name == 'lalc_backend/recognize/nn_classifier.py'
                             or (name.startswith('lalc_backend/ai/model/mirror_')
                                 and name.endswith('.txt'))}
        models = {}
        for name in ('mirror_legend', 'mirror_path'):
            member = f'lalc_backend/ai/model/{name}/best_model.onnx'
            body = source.read(member)
            native = adapter(body)
            (bundle / 'model/classify' / (name + '.onnx')).write_bytes(native)
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(body, options, providers=['CPUExecutionProvider'])
            adapted = ort.InferenceSession(native, options, providers=['CPUExecutionProvider'])
            models[name] = dict(session=session, adapted=adapted,
                                model_sha256=hashlib.sha256(body).hexdigest(),
                                adapter_sha256=hashlib.sha256(native).hexdigest())
        resource = Resource()
        wait_job(resource.post_bundle(bundle), timeout=30)
        controller = ReplayController(image)
        wait_job(controller.post_connection(), timeout=10)
        tasker = Tasker()
        if not tasker.bind(resource, controller):
            raise ValueError('Offline native resource binding failed')
        for name, model in models.items():
            session = model['session']
            height, width = session.get_inputs()[0].shape[-2:]
            for role, box in crops:
                x, y, w, h = box
                pixels = cv2.resize(image[y:y+h, x:x+w], (width, height), interpolation=cv2.INTER_AREA)
                rgb = pixels[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
                tensor = rgb.copy()
                tensor = (tensor - np.asarray([.485, .456, .406], np.float32).reshape(1, 3, 1, 1))
                tensor /= np.asarray([.229, .224, .225], np.float32).reshape(1, 3, 1, 1)
                expected = session.run(None, {session.get_inputs()[0].name: tensor})[0].reshape(-1)
                adapted = model['adapted']
                adapter_logits = adapted.run(None, {adapted.get_inputs()[0].name: rgb})[0].reshape(-1)
                error = float(np.max(np.abs(adapter_logits - expected)))
                if adapter_logits.shape != expected.shape or error > 1e-4:
                    raise ValueError('Adapter/supplier logits differ: ' + str(error))
                job = tasker.post_recognition(JRecognitionType.NeuralNetworkClassify,
                    JNeuralNetworkClassify(model=name + '.onnx'), pixels)
                wait_job(job, timeout=30)
                detail = job.get()
                if not detail or not detail.nodes or not detail.nodes[-1].recognition:
                    raise ValueError('Native classifier result absent')
                recognition = detail.nodes[-1].recognition
                raw = recognition.raw_detail
                results = raw.get('all') or raw.get('all_results') or []
                if len(results) != 1:
                    raise ValueError('Native top classification unavailable')
                top = results[0]
                probs = np.exp(expected - expected.max())
                probs /= probs.sum()
                top_score_error = abs(float(top['score']) - float(probs.max()))
                if int(top['cls_index']) != int(expected.argmax()) or top_score_error > 1e-5:
                    raise ValueError('Native top class/score differs: ' + repr(top))
                rows.append(dict(model=name, region_role=role, crop=box,
                                 reference_logits=expected.tolist(),
                                 adapter_logits_max_abs_error=error,
                                 native_top=top, native_top_score_abs_error=top_score_error,
                                 model_sha256=model['model_sha256'],
                                 adapter_sha256=model['adapter_sha256']))
        assert controller.attempts == []
    report = dict(passed=True, supplier_revision=revision, frame=str(frame.relative_to(ROOT)),
                  source_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                  source_preprocessing_and_labels=source_provenance,
                  frame_sha256=hashlib.sha256(frame.read_bytes()).hexdigest(), rows=rows,
                  recognizer='MaaFramework.NeuralNetworkClassify', game_controller=False,
                  input_sent=False, trained_locally=False, input_authorized=False,
                  quality_passed=False, production_enabled=False,
                  native_full_logits_available=False,
                  resize='cv2.INTER_AREA shared native/reference probe; not supplier PIL path preprocessing',
                  scope='ORT full-logit adapter parity plus Maa native top class/score parity; no box detection, dataset quality or live steering acceptance')
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, samples=len(rows), out=str(args.out), input_sent=False)))


if __name__ == '__main__':
    main()

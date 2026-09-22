import fs from 'node:fs';
import vm from 'node:vm';

const [mode, assetDir, textPath, inOrOut, maybeOut] = process.argv.slice(2);
const context = {
  console,
  setTimeout,
  clearTimeout,
  atob: globalThis.atob,
  btoa: globalThis.btoa,
  TextDecoder,
  TextEncoder,
  URL,
  Buffer,
};
context.window = context;
context.self = context;
context.globalThis = context;
vm.createContext(context);

function load(name) {
  const path = `${assetDir}/${name}`;
  vm.runInContext(fs.readFileSync(path, 'utf8'), context, { filename: path });
}

if (mode === 'detect') {
  load('term-typing.js');
  load('novel-scan-policy.js');
  load('novel-term-detector.js');
  const text = fs.readFileSync(textPath, 'utf8');
  const result = context.NovelTermDetector.detectTerms(text, {
    maxResults: 2000,
    profile: 'auto',
    includeVietnamese: false,
    includeMeta: true,
    disableDictConflict: true,
    lineSpreadRescue: true,
    onProgress(step) {
      console.error(`scan ${step.phase} ${step.percent}%`);
    },
  });
  const terms = (result.terms || []).map((term) => ({
    zh: term.zh,
    category: term.category || '',
    count: term.count || 0,
    confidence: term.confidence,
    reasons: term.reasons,
    features: term.features,
    target: term.target,
  }));
  fs.writeFileSync(inOrOut, JSON.stringify({ terms }));
  console.error(`detected ${terms.length}`);
} else if (mode === 'split') {
  load('term-typing.js');
  load('term-verifier.js');
  load('term-verifier-cascade.js');
  load('novel-term-detector.js');
  const payload = JSON.parse(fs.readFileSync(inOrOut, 'utf8'));
  const text = fs.readFileSync(textPath, 'utf8');
  const phienam = payload.phienam || {};
  function hanviet(value) {
    const parts = [];
    for (const ch of String(value || '')) {
      const reading = phienam[ch];
      if (!reading) return '';
      parts.push(reading);
    }
    return parts.join(' ');
  }
  context.DictEngine = { isReady: true, hanviet };
  const terms = payload.terms || [];
  const model = JSON.parse(fs.readFileSync(`${assetDir}/term-verifier-v30r-cascade.json`, 'utf8'));
  model.guard = JSON.parse(fs.readFileSync(`${assetDir}/term-verifier-v15-gbdt.json`, 'utf8'));
  const stats = context.TermVerifier.annotateTerms(model, terms, {
    keep: Number(model.keepThreshold || model.threshold || 0.5),
    review: Number(model.reviewThreshold || 0.35),
    autoIgnoreRejects: model.autoIgnoreRejects === true,
    fullText: text,
  });
  function pack(term) {
    const rules = term.verifier && Array.isArray(term.verifier.rules) ? term.verifier.rules.join(',') : '';
    return {
      zh: term.zh,
      vi: String(term.vi || '').replace(/\t/g, ' '),
      category: term.category || '',
      count: term.count || 0,
      score: term.verifier ? term.verifier.keepScore : 0,
      rules,
    };
  }
  const review = [];
  const reject = [];
  for (const term of terms) {
    if (!term.vi) {
      term.vi = context.NovelTermDetector.suggestVietnamese(term.zh, { category: term.category });
    }
    const decision = term.verifier && term.verifier.decision;
    if (decision === 'review') review.push(pack(term));
    else if (decision === 'reject') reject.push(pack(term));
  }
  fs.writeFileSync(maybeOut, JSON.stringify({ stats, review, reject }));
  console.error(JSON.stringify(stats));
} else {
  console.error(`mode không hỗ trợ: ${mode}`);
  process.exit(2);
}

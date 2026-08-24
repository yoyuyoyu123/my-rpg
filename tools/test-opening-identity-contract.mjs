import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const rules = fs.readFileSync(new URL('../backend/app/domain/rules.py', import.meta.url), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

// The UI must distinguish an intentional random draw from an unset profession.
assert(html.includes('data-group="pref-prof" data-val="__random__"'), 'profession random chip lost its explicit marker');
assert(!html.includes('data-group="pref-prof" data-val="">'), 'profession random chip still uses the ambiguous empty value');

// “无额外强调” remains the only explicit no-profession choice; empty legacy
// saves and the new random marker both continue to draw from the profile.
assert(/if\(PREFS\.prof==='__none__'\)\{\s*prof='';/.test(html), 'explicit no-profession choice is not preserved');
assert(/else if\(!PREFS\.prof\|\|PREFS\.prof==='__random__'\)\{[\s\S]*?profileCandidate\('profession',profile\.professions\)/.test(html), 'random profession choice no longer uses the selected profile');
assert(/var total=0,weights=list\.map\(function\(t\)\{var w=catId==='profession'\?1:/.test(html), 'profession sampling still uses research frequency');
const profileBlock = html.slice(html.indexOf('var RANDOM_PROFILES='), html.indexOf('var PROFILE_BY_SKELETON='));
assert(!profileBlock.includes('医生'), 'doctor remains in a generic random profile pool');
assert(/'冒险探索':\['adventure','rivalry','relationship','building'\]/.test(html), 'adventure direction is still locked to one profile');
assert(html.includes('fast:!!trans.fast'), 'transmigration state does not preserve fast-route metadata');
assert(html.includes('else if(old===2||old===3)phase=4'), 'fast migration still requires a separate full turn for transit');
assert(html.includes('目标世界身份参考：'), 'transmigration identity scope is not separated from origin life');
assert(html.includes("targetScope+'故事引擎：'"), 'transmigration story engine still leaks into origin-life scope');

// The backend rule remains identity-open rather than injecting a second list of bans.
assert(rules.includes('身份开放规则——覆盖各世界观中的固定列表'), 'backend identity rule was removed');

console.log('opening identity contract: passed');

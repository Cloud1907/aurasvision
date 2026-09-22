const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function filters(){
  const ctx=vm.createContext({window:{},URLSearchParams,Date});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/event-filters.js'),'utf8'),ctx);
  return ctx.window.EventFilters;
}
test('combined query preserves search text and converts local dates to UTC',()=>{
  const f=filters();
  const params=new URLSearchParams(f.query({tur:'telefon',kamera:'front & back',q:'34 ABC',start:'2026-09-22T10:00',end:'2026-09-22T11:00',offset:50}));
  assert.equal(params.get('kamera'),'front & back');
  assert.equal(params.get('q'),'34 ABC');
  assert.equal(params.get('start'),new Date('2026-09-22T10:00').toISOString());
  assert.equal(params.get('offset'),'50');
  assert.equal(params.get('limit'),'51');
});
test('invalid range is rejected before requesting results',()=>{
  assert.throws(()=>filters().query({start:'2026-09-23T10:00',end:'2026-09-22T10:00'}));
});
test('reset removes every active filter and pagination',()=>{
  assert.equal(filters().query(filters().defaults()),'limit=51&offset=0');
});

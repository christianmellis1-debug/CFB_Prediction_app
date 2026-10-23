const assert=require('node:assert/strict');
const test=require('node:test');
const core=require('../bet_tracker/core.js');
const receipts=require('../bet_tracker/receipt_parser.js');

const game={id:'123',home:'Texas',away:'Oklahoma',season:2026,week:8,completed:true,homeScore:28,awayScore:24};
function bet(fields={}){
  return core.validate({id:'test-1',gameId:'123',home:'Texas',away:'Oklahoma',team:'Texas',created:'2026-10-23T12:00:00Z',season:2026,week:8,stake:10,odds:-110,book:'DraftKings',override:'Auto',autoResult:'Pending',receiptReturn:null,...fields});
}
test('older moneyline tickets remain valid and still grade',()=>{
 const b=bet();
 assert.equal(b.market,'moneyline');
 assert.equal(core.grade(b,[game]).autoResult,'Won');
 assert.equal(core.grade({...b,team:'Oklahoma'},[game]).autoResult,'Lost');
});
test('underdog spread grades against the correct adjusted margin',()=>{
 assert.equal(core.grade(bet({market:'spread',team:'Oklahoma',line:5.5}),[game]).autoResult,'Won');
 assert.equal(core.grade(bet({market:'spread',team:'Oklahoma',line:3.5}),[game]).autoResult,'Lost');
 assert.equal(core.grade(bet({market:'spread',team:'Oklahoma',line:4}),[game]).autoResult,'Push');
});
test('favorite spread and unfinished games',()=>{
 assert.equal(core.grade(bet({market:'spread',team:'Texas',line:-3.5}),[game]).autoResult,'Won');
 assert.equal(core.grade(bet({market:'spread',team:'Texas',line:-4}),[game]).autoResult,'Push');
 assert.equal(core.grade(bet({market:'spread',team:'Texas',line:-5}),[game]).autoResult,'Lost');
 assert.equal(core.grade(bet({market:'spread',team:'Texas',line:-3}),[{...game,completed:false}]).autoResult,'Pending');
});
test('totals grade Over/Under and pushes',()=>{
 assert.equal(core.grade(bet({market:'total',team:'',side:'Over',line:49.5}),[game]).autoResult,'Won');
 assert.equal(core.grade(bet({market:'total',team:'',side:'Under',line:49.5}),[game]).autoResult,'Lost');
 assert.equal(core.grade(bet({market:'total',team:'',side:'Under',line:52}),[game]).autoResult,'Push');
 assert.equal(core.grade(bet({market:'total',team:'',side:'Over',line:53}),[game]).autoResult,'Lost');
});
test('reject invalid lines and selections before saving',()=>{
 assert.throws(()=>bet({market:'spread',line:''}),/line/);
 assert.throws(()=>bet({market:'total',side:'',line:45}),/Over or Under/);
 assert.throws(()=>bet({market:'spread',team:'',line:4}),/Pick/);
});
test('screenshot provenance and receipt ID survive edits and validation',()=>{
 const b=bet({source:'screenshot',receiptId:'ABC12345',placedAt:'Oct 23 2026',market:'spread',line:-3.5});
 assert.equal(core.validate({...b,odds:-115}).source,'screenshot');
 assert.equal(b.receiptId,'ABC12345');
 assert.equal(b.line,-3.5);
});
test('moneyline OCR extracts stake, odds, payout and ticket ID',()=>{
 const r=receipts.parse('Single\nMoneyline\nTexas -110\nWager: $10.00\nPotential Payout: $19.09\nTicket ID: ABC123456');
 assert.equal(r.market,'moneyline');
 assert.equal(r.odds,-110);
 assert.equal(r.stake,10);
 assert.equal(r.receiptReturn,19.09);
 assert.equal(r.receiptId,'ABC123456');
 assert.equal(r.unsupported,false);
});
test('spread OCR recognizes lines and to-win amount as profit not total',()=>{
 const r=receipts.parse('Point Spread\nTexas -3.5 (-110)\nWager $20.00\nTo Win $18.18');
 assert.equal(r.market,'spread');
 assert.equal(r.line,-3.5);
 assert.equal(r.odds,-110);
 assert.equal(r.receiptReturn,38.18);
});
test('total OCR recognizes selection and total line',()=>{
 const r=receipts.parse('Total Points\nOver 48.5\nOdds -115\nStake $10\nTotal Payout $18.70');
 assert.equal(r.market,'total');
 assert.equal(r.side,'Over');
 assert.equal(r.line,48.5);
 assert.equal(r.odds,-115);
});
test('parlays are detected and not eligible for automatic import',()=>{
 const r=receipts.parse('Same Game Parlay\nTexas -110\nWager $10.00');
 assert.equal(r.unsupported,true);
});

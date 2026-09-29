import test from "node:test";
import assert from "node:assert/strict";
import {ElementRegistry, createElement} from "./ElementRegistry.js";
import {evaluateProgram, OPERATIONS} from "./evaluate.js";
import {geometryBounds} from "./bounds.js";

test("factories follow moving data and propagate phase visibility to every part", () => {
  for (const kind of ["ball", "particle", "vector_arrow", "vehicle", "cart"]) {
    let position = [2, 0];
    const calls = [];
    const board = {create(type, args, options) {
      const item = {type,args,options,setAttribute(a) {Object.assign(this.options,a);}};
      calls.push(item); return item;
    }};
    const element = createElement({board, view:{kind,radius:.2,glow:true,mass:2},
      data:() => position, origin:() => [1,1], options:{strokeColor:"red"}});
    assert.ok(ElementRegistry[kind]);
    element.setAttribute({visible:false});
    assert.ok(calls.every(c => c.options.visible === false));
    position = [3, 4];
    if (kind === "vector_arrow") assert.deepEqual(calls[0].args[1].map(f => f()), [4,5]);
    if (kind === "ball") assert.deepEqual(calls.at(-1).args[0].map(f => f()), position);
    if (kind === "cart") assert.equal(calls[0].args[0][0](), 2.4);
  }
});
test("unknown names cannot resolve through prototype properties", () => {
  assert.throws(() => createElement({view:{kind:"constructor"}}), /Unsupported/);
});

test("camera fits rotating vector endpoints at extreme interactive parameters", () => {
  const plan = {x_range:[-5,5],y_range:[-4,4],visuals:[
    {id:"v",kind:"vector_arrow",data:"v",origin:"p"},
  ]};
  let first;
  for (let i=0; i<24; i++) {
    const a=i*Math.PI/12, p=[4*Math.cos(a),4*Math.sin(a)], v=[-6*Math.sin(a),6*Math.cos(a)];
    const bounds=geometryBounds(plan,{p,v},{},["v"]);
    const end=p.map((n,j)=>n+v[j]);
    assert.ok(end[0]>bounds[0] && end[0]<bounds[2] && end[1]>bounds[3] && end[1]<bounds[1]);
    if (first) bounds.forEach((n,j)=>assert.ok(Math.abs(n-first[j])<1e-12));
    else first=bounds;
  }
});

test("predicted symbols feed the next lookup rather than reveal a fixed answer", () => {
  const plan = {kind:"composition", nodes:[
    {id:"seed",op:"parameter",value:0,min:0,max:2},
    {id:"scores",op:"constant",value:[[0,3,1],[1,0,3],[3,1,0]]},
    {id:"prefix",op:"vector",args:["seed"]},
  ]};
  let last = "seed";
  for (let i=0; i<3; i++) {
    plan.nodes.push(
      {id:`logits-${i}`,op:"row",args:["scores",last]},
      {id:`probs-${i}`,op:"softmax",args:[`logits-${i}`]},
      {id:`choice-${i}`,op:"argmax",args:[`probs-${i}`]},
      {id:`token-${i}`,op:"vector",args:[`choice-${i}`]},
    );
    last = `choice-${i}`;
  }
  plan.nodes.push({id:"sequence",op:"concat",args:["prefix","token-0","token-1","token-2"]});
  for (const seed of [0,1,2]) {
    const values = evaluateProgram(plan, {sceneId:"s",overrides:{"s-program.seed":seed}});
    assert.deepEqual(values.sequence, [0,1,2,3].map(i => (seed+i)%3));
    assert.ok(Math.abs(values["probs-0"].reduce((a,b)=>a+b,0)-1)<1e-12);
  }
  assert.equal(OPERATIONS.argmax([2,2,1]), 0, "ties choose the first index");
  assert.throws(() => OPERATIONS.row([[1,2]], 1), /out of range/);
});

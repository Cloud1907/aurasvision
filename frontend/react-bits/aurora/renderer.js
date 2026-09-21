import { VERT, FRAG } from './shaders';

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source); gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) { gl.deleteShader(shader); throw new Error('Arka plan shader derlenemedi'); }
  return shader;
}
function createProgram(gl) {
  const vertex = compile(gl, gl.VERTEX_SHADER, VERT), fragment = compile(gl, gl.FRAGMENT_SHADER, FRAG);
  const program = gl.createProgram();
  gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
  gl.deleteShader(vertex); gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { gl.deleteProgram(program); throw new Error('Arka plan programı oluşturulamadı'); }
  return program;
}
function configure(gl, program) {
  gl.useProgram(program);
  const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'position'); gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  gl.uniform1f(gl.getUniformLocation(program, 'uAmplitude'), 1.3);
  gl.uniform1f(gl.getUniformLocation(program, 'uBlend'), 0.65);
  gl.uniform1f(gl.getUniformLocation(program, 'uLightMode'), 0);
  gl.uniform3fv(gl.getUniformLocation(program, 'uColorStops[0]'), new Float32Array([0.38,0.18,1, 0.12,0.7,1, 0.86,0.2,0.67]));
  return buffer;
}
export function createAurora(canvas) {
  const gl = canvas.getContext('webgl2', { alpha: true, antialias: false, powerPreference: 'low-power', premultipliedAlpha: true });
  if (!gl) return null;
  const program = createProgram(gl), buffer = configure(gl, program);
  const time = gl.getUniformLocation(program, 'uTime'), resolution = gl.getUniformLocation(program, 'uResolution');
  const resize = () => {
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.min(1200, Math.round(r.width * 0.75)));
    canvas.height = Math.max(1, Math.min(550, Math.round(r.height * 0.75)));
    gl.viewport(0, 0, canvas.width, canvas.height); gl.uniform2f(resolution, canvas.width, canvas.height);
  };
  resize(); const observer = new ResizeObserver(resize); observer.observe(canvas);
  return {
    draw(ms) { gl.uniform1f(time, ms * 0.00035); gl.drawArrays(gl.TRIANGLES, 0, 3); },
    dispose() { observer.disconnect(); gl.deleteBuffer(buffer); gl.deleteProgram(program); }
  };
}

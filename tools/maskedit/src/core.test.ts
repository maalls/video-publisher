import { describe, expect, it } from 'vitest'
import { cleanup, flatness, translateKey, addKeyframe, addPoint, movePoint, newDoc, nearestEdge, pointsAt, removeKeyframe, removePoint, validate } from './core'

const square: [number, number][] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]

describe('maskedit core', () => {
  it('interpolates points linearly between keyframes', () => {
    let d = newDoc('c', 16, [832, 480], 64)
    d = addKeyframe(d, 0, square)
    d = addKeyframe(d, 40)
    d = movePoint(d, 40, 0, [0.3, 0.3])
    const p = pointsAt(d, 20)
    expect(p[0][0]).toBeCloseTo(0.2)
    expect(p[1][0]).toBeCloseTo(0.5)
  })
  it('holds the first and last keyframe outside the range', () => {
    let d = addKeyframe(newDoc('c', 16, [832, 480], 64), 10, square)
    expect(pointsAt(d, 0)).toEqual(square)
    expect(pointsAt(d, 63)).toEqual(square)
  })
  it('adding a point keeps every keyframe at the same point count and shape', () => {
    let d = addKeyframe(newDoc('c', 16, [832, 480], 64), 0, square)
    d = addKeyframe(d, 30)
    d = addPoint(d, 0, 1, [0.3, 0.1])
    expect(d.keyframes.every((k) => k.points.length === 5)).toBe(true)
    expect(d.keyframes[1].points[1]).toEqual([0.3, 0.1])
    expect(validate(d)).toEqual([])
    d = removePoint(d, 1)
    expect(d.keyframes.every((k) => k.points.length === 4)).toBe(true)
  })
  it('new keyframe starts from the interpolated shape; remove works', () => {
    let d = addKeyframe(newDoc('c', 16, [832, 480], 64), 0, square)
    d = addKeyframe(d, 40)
    d = movePoint(d, 40, 2, [0.9, 0.9])
    d = addKeyframe(d, 20)
    expect(d.keyframes.find((k) => k.frame === 20)!.points[2][0]).toBeCloseTo(0.7)
    d = removeKeyframe(d, 20)
    expect(d.keyframes.length).toBe(2)
  })
  it('finds the nearest edge for inserting a point', () => {
    expect(nearestEdge(square, [0.3, 0.09]).index).toBe(1)
    expect(nearestEdge(square, [0.51, 0.3]).index).toBe(2)
  })

  it('translateKey moves the whole key and keeps the shape inside the frame', () => {
    const d = addKeyframe(newDoc('c', 16, [832, 480], 10), 0, square)
    const a = translateKey(d, 0, square, 0.2, 0.1)
    expect(a.keyframes[0].points[0][0]).toBeCloseTo(0.3)
    expect(a.keyframes[0].points[2][1]).toBeCloseTo(0.6)
    const b = translateKey(d, 0, square, 5, -5)
    expect(b.keyframes[0].points[1][0]).toBeCloseTo(1)
    expect(b.keyframes[0].points[0][1]).toBeCloseTo(0)
    expect(b.keyframes[0].points[1][0] - b.keyframes[0].points[0][0]).toBeCloseTo(0.4)
  })

  it('cleanup removes points that are straight on every key, keeps the others and at least 3', () => {
    // square with an extra point in the middle of the top edge, on key 0 and key 10
    const sq: [number, number][] = [[0.1, 0.1], [0.3, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
    let d = newDoc('c', 16, [1000, 1000], 20)
    d = addKeyframe(d, 0, sq)
    d = addKeyframe(d, 10)
    const r = cleanup(d)
    expect(r.removed).toBe(1)
    expect(r.doc.keyframes[0].points.length).toBe(4)
    // point 1 is bent on key 10 only: it must be kept
    const bent = movePoint(d, 10, 1, [0.3, 0.2])
    expect(cleanup(bent).removed).toBe(0)
    // never below 3 points
    const tri = addKeyframe(newDoc('c', 16, [1000, 1000], 5), 0, [[0, 0], [0.5, 0.0], [1, 0]])
    expect(cleanup(tri).doc.keyframes[0].points.length).toBe(3)
    expect(flatness(sq, 1, [1000, 1000]).angle).toBeCloseTo(0)
  })
})

import type { Keypoint } from '../types'

/**
 * 关键点索引与后端 detector.py 的 DEFAULT_KEYPOINT_NAMES 一致（COCO 17 点）：
 * 0 nose, 1 left_eye, 2 right_eye, 3 left_ear, 4 right_ear,
 * 5 left_shoulder, 6 right_shoulder, 7 left_elbow, 8 right_elbow,
 * 9 left_wrist, 10 right_wrist, 11 left_hip, 12 right_hip,
 * 13 left_knee, 14 right_knee, 15 left_ankle, 16 right_ankle
 */
export const COCO_SKELETON: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [0, 2], [1, 3], [2, 4],            // 颅部
  [5, 6],                                     // 双肩
  [5, 7], [7, 9],                             // 左臂
  [6, 8], [8, 10],                            // 右臂
  [5, 11], [6, 12],                           // 躯干
  [11, 12],                                   // 双髋
  [11, 13], [13, 15],                         // 左腿
  [12, 14], [14, 16],                         // 右腿
  [0, 5], [0, 6],                             // 头-肩
]

/** 前端只绘制较稳定的关键点，避免遮挡部位的低置信度猜测点产生误导连线。 */
export const KEYPOINT_CONFIDENCE_THRESHOLD = 0.5

/** 低置信度但仍可见（≥阈值）的关键点，前端用更暗的样式呈现。 */
export const KEYPOINT_DIM_THRESHOLD = 0.68

export function isKeypointVisible(
  kpt: Keypoint | undefined,
  threshold: number = KEYPOINT_CONFIDENCE_THRESHOLD,
): boolean {
  return !!kpt && kpt.confidence >= threshold
}

export interface NormalizedKeypoint {
  index: number
  kpt: Keypoint
  leftPct: number
  topPct: number
  dim: boolean
}

/**
 * 将关键点像素坐标归一化为容器内百分比，复用 boxStyle 的口径，
 * 使点/线与 .box 标注框、视频画面精确对齐。
 */
export function normalizeKeypoint(
  index: number,
  kpt: Keypoint,
  width: number,
  height: number,
): NormalizedKeypoint {
  return {
    index,
    kpt,
    leftPct: width > 0 ? (kpt.x / width) * 100 : 0,
    topPct: height > 0 ? (kpt.y / height) * 100 : 0,
    dim: kpt.confidence < KEYPOINT_DIM_THRESHOLD,
  }
}

export interface SkeletonEdge {
  x1: number
  y1: number
  x2: number
  y2: number
}

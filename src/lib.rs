use numpy::ndarray::{s, ArrayView1};
use numpy::PyReadonlyArray2;
use pyo3::prelude::*;

use numpy::PyReadonlyArray1;

#[pymodule]
fn rust_analysis(_py: Python, m: &PyModule) -> PyResult<()> {
    fn l2_norm(a: &[f32]) -> f32 {
        let sum_of_squares: f32 = a.iter().map(|&x| x * x).sum();
        sum_of_squares.sqrt()
    }
    fn db_diff(power_db_f1: ArrayView1<f32>, power_db_f2: ArrayView1<f32>) -> f32 {
        let max_f1 = power_db_f1
            .iter()
            .cloned()
            .fold(f32::NEG_INFINITY, f32::max);
        let max_f2 = power_db_f2
            .iter()
            .cloned()
            .fold(f32::NEG_INFINITY, f32::max);
        (max_f1 - max_f2).abs()
    }
    #[pyfn(m)]
    fn detect_loop_pairs(
        chroma: PyReadonlyArray2<f32>,
        power_db: PyReadonlyArray2<f32>,
        beats: PyReadonlyArray1<usize>,
        acceptable_chroma_deviation: PyReadonlyArray1<f32>,
        min_loop_duration: usize,
        max_loop_duration: usize,
        acceptable_loudness_difference: f32,
    ) -> Vec<(usize, usize, f32, f32)> {
        let mut candidate_pairs: Vec<(usize, usize, f32, f32)> = Vec::new();

        let chroma = chroma.as_array();
        let power_db = power_db.as_array();
        let beats = beats.as_slice().unwrap_or(&[]);

        for (idx, &loop_end) in beats.iter().enumerate() {
            for &loop_start in beats.iter() {
                let loop_length = loop_end - loop_start;
                if loop_length < min_loop_duration {
                    break;
                }
                if loop_length > max_loop_duration {
                    continue;
                }

                let note_distance = l2_norm(
                    (&chroma.slice(s![.., loop_end]) - &chroma.slice(s![.., loop_start]))
                        .as_slice()
                        .unwrap_or(&[]),
                );

                if note_distance <= *acceptable_chroma_deviation.get(idx).unwrap() {
                    let loudness_difference = db_diff(
                        power_db.slice(s![.., loop_end]),
                        power_db.slice(s![.., loop_start]),
                    );

                    if loudness_difference <= acceptable_loudness_difference {
                        candidate_pairs.push((
                            loop_start,
                            loop_end,
                            note_distance,
                            loudness_difference,
                        ));
                    }
                }
            }
        }

        return candidate_pairs;
    }
    Ok(())
}

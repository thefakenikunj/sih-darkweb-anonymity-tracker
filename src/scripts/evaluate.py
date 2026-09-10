import sys
import pandas as pd
from typing import Dict, List, Tuple

def evaluate_resolution(predictions: List[Dict], ground_truth: List[Dict], threshold: float = 0.75) -> Dict[str, float]:
    """
    Calculates Precision, Recall, and F1-score for identity resolution matches.
    
    predictions: List of dicts with keys ['dark_id', 'clear_id', 'score']
    ground_truth: List of dicts with keys ['dark_id', 'clear_id', 'is_match']
    """
    gt_map = {(gt['dark_id'], gt['clear_id']): gt['is_match'] for gt in ground_truth}
    
    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for pred in predictions:
        pair = (pred['dark_id'], pred['clear_id'])
        predicted_match = pred['score'] >= threshold
        actual_match = gt_map.get(pair, False)

        if predicted_match and actual_match:
            tp += 1
        elif predicted_match and not actual_match:
            fp += 1
        elif not predicted_match and actual_match:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4)
    }

if __name__ == "__main__":
    # Sample execution against benchmark ground truth
    mock_predictions = [
        {"dark_id": "dw_101", "clear_id": "clearnet_201", "score": 0.92},
        {"dark_id": "dw_102", "clear_id": "clearnet_205", "score": 0.81},
        {"dark_id": "dw_103", "clear_id": "clearnet_209", "score": 0.40},
    ]
    
    mock_ground_truth = [
        {"dark_id": "dw_101", "clear_id": "clearnet_201", "is_match": True},
        {"dark_id": "dw_102", "clear_id": "clearnet_205", "is_match": False}, # False Positive
        {"dark_id": "dw_103", "clear_id": "clearnet_209", "is_match": False},
    ]

    results = evaluate_resolution(mock_predictions, mock_ground_truth, threshold=0.75)
    
    print("=" * 45)
    print(" IDENTITY RESOLUTION EVALUATION METRICS")
    print("=" * 45)
    for key, value in results.items():
        print(f" {key.replace('_', ' ').title():<25}: {value}")
    print("=" * 45)
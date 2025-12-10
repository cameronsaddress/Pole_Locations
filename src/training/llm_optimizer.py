
import os
import json
import logging
import requests
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LLMHyperparameterOptimizer:
    def __init__(self, api_key: str = None, model: str = "x-ai/grok-4.1-fast"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.history: List[Dict[str, Any]] = []
        
        if not self.api_key:
            logger.warning("No OpenRouter API key provided. LLM Optimization will fail.")

    def suggest_hyperparameters(self, current_best: Dict, recent_trials: List[Dict]) -> Dict:
        """
        Consults the LLM to suggest the next set of hyperparameters based on previous performance.
        """
        
        system_prompt = """
        You are an expert AI Research Engineer specializing in YOLOv8 Object Detection optimization. 
        Your goal is to maximize mAP50 (Mean Average Precision) while minimizing Box Loss.
        
        STRATEGY:
        1. If Box Loss is oscillating, reduce 'lr0' (Learning Rate) and increase 'momentum'.
        2. If mAP is plateauing significantly below 0.90, try slightly increasing 'lr0' or reducing 'weight_decay'.
        3. If overfitting is detected (Validation Loss >> Training Loss), increase 'weight_decay'.
        4. Make incremental changes. Do not swing parameters wildly unless early trials show poor convergence.
        
        Output a JSON object ONLY containing the recommended hyperparameters for the next trial.
        Do not include markdown formatting or explanation. Just the JSON.
        
        The hyperparameters to tune are:
        - lr0 (initial learning rate): float between 0.0001 and 0.01
        - momentum: float between 0.8 and 0.99
        - weight_decay: float between 0.0001 and 0.001
        - epochs: int (suggest small gains, e.g. 50-150)
        """
        
        user_prompt = f"""
        GOAL: Achieve mAP50 > 0.92
        
        Current Best Performance: {json.dumps(current_best)}
        
        Recent Trials History:
        {json.dumps(recent_trials[-5:])}
        
        Based on this data, reason about the convergence stability and overfitting risk.
        Propose the next experimental configuration (Trial #{len(self.history) + 1}).
        """
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2, # Low temperature for more deterministic/rational tuning
            "response_format": {"type": "json_object"}
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://polevision.ai", 
            "X-Title": "PoleVision Enterprise"
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            content = result['choices'][0]['message']['content']
            logger.info(f"LLM Reasoning: {content}")
            
            # Parse JSON from LLM
            params = json.loads(content)
            
            # Validate ranges (sanity check)
            params['lr0'] = max(0.0001, min(0.01, params.get('lr0', 0.01)))
            params['epochs'] = int(params.get('epochs', 100))
            
            return params
            
        except Exception as e:
            logger.error(f"LLM Optimization Failed: {e}")
            # Fallback to safe defaults if LLM fails
            return {
                "lr0": 0.01,
                "momentum": 0.937,
                "weight_decay": 0.0005,
                "epochs": 100
            }

    def log_result(self, params: Dict, metrics: Dict):
        """Record the result of a training run for context in the next iteration."""
        self.history.append({
            "params": params,
            "metrics": metrics
        })

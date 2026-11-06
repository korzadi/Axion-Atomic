import os
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from peft import LoraConfig
from trl import SFTTrainer

MODEL = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
DATA = os.getenv("TRAIN_FILE", "data/train.jsonl")
OUT = os.getenv("OUTPUT_DIR", "output/qwen-coder-lora")

def main():
    if not torch.cuda.is_available():
        raise SystemExit("Use a supported external CUDA GPU; do not train on the VPS.")
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=quant,
                                                  device_map="auto", trust_remote_code=False)
    ds = load_dataset("json", data_files=DATA, split="train")
    ds = ds.map(lambda row: {"text":tok.apply_chat_template(row["messages"],
                    tokenize=False, add_generation_prompt=False)})
    args = TrainingArguments(output_dir=OUT, num_train_epochs=1, learning_rate=2e-4,
        per_device_train_batch_size=1, gradient_accumulation_steps=16,
        gradient_checkpointing=True, logging_steps=10, save_steps=100,
        bf16=torch.cuda.is_bf16_supported(), fp16=not torch.cuda.is_bf16_supported(),
        optim="paged_adamw_8bit", report_to="none")
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM", target_modules=["q_proj","k_proj","v_proj","o_proj",
        "gate_proj","up_proj","down_proj"])
    trainer = SFTTrainer(model=model, args=args, train_dataset=ds,
                         peft_config=lora, processing_class=tok)
    trainer.train()
    trainer.save_model(OUT)
    tok.save_pretrained(OUT)

if __name__ == "__main__":
    main()

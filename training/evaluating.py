from utils import logging
import os
import torch
import numpy as np
from metrics import calculate_metrics
from tqdm.auto import tqdm


def evaluate(args, model, eval_dataloader, tokenizer, accelerator=None):
    eval_output_dir = args.output_dir
    if not os.path.exists(eval_output_dir):
        os.makedirs(eval_output_dir)

    if accelerator and accelerator.is_main_process:
        logging.info("***** Running evaluation *****")
        logging.info(f"  Num examples = {len(eval_dataloader) * args.eval_batch_size}")
        logging.info(f"  Batch size = {args.eval_batch_size}")

    eval_loss = 0.0
    nb_eval_steps = 0
    all_bleu_score = []
    model.eval()

    for batch in tqdm(eval_dataloader, desc="Evluating:", disable=not accelerator.is_local_main_process):
        in_ids = batch['source_ids'].to(args.device)
        in_masks = batch['source_mask'].to(args.device)
        target_ids = batch['target_ids'].to(args.device)
        with torch.no_grad():

            #calculate loss
            loss = model(in_ids, in_masks, target_ids)

            if accelerator:
                loss = accelerator.gather(loss)

            eval_loss += loss.mean().item()

            # generate comments
            generate_ids = model.generate(
                input_ids=in_ids,
                attention_mask=in_masks,
                max_length=512,
                num_beams=4,
                early_stopping=True,
                no_repeat_ngram_size=2,
            )

            # decode generated and actual comments
            generated_comments = tokenizer.batch_decode(generate_ids, skip_special_tokens=True,
                                                        clean_up_tokenization_spaces=True)
            actual_comments = tokenizer.batch_decode(target_ids, skip_special_tokens=True,
                                                     clean_up_tokenization_spaces=True)

            # calculating BLEU score
            bleu_score = calculate_metrics(generated_comments, actual_comments)

            all_bleu_score.append(bleu_score)
        nb_eval_steps += 1

    #calculate avg
    avg_bleu_score = np.mean(all_bleu_score) if all_bleu_score else 0
    eval_loss = eval_loss / nb_eval_steps
    perplexity = torch.tensor(eval_loss)

    result = {
        "eval_loss": float(perplexity),
        "eval_bleu_score": avg_bleu_score,
    }
    return result
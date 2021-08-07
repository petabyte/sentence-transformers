import csv
import gzip
import os
import unittest
import shutil

from torch.utils.data import DataLoader

from sentence_transformers import SentenceTransformer, SentencesDataset, losses, models, util
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
from sentence_transformers.readers import InputExample


class SaveOptimizerTest(unittest.TestCase):
    test_model_paths = ['./sample/model','./sample/5']

    def setUp(self):
        sts_dataset_path = 'datasets/stsbenchmark.tsv.gz'
        if not os.path.exists(sts_dataset_path):
            util.http_get('https://sbert.net/datasets/stsbenchmark.tsv.gz', sts_dataset_path)

        nli_dataset_path = 'datasets/AllNLI.tsv.gz'
        if not os.path.exists(nli_dataset_path):
            util.http_get('https://sbert.net/datasets/AllNLI.tsv.gz', nli_dataset_path)

        #Read NLI
        label2int = {"contradiction": 0, "entailment": 1, "neutral": 2}
        self.nli_train_samples = []
        max_train_samples = 10000
        with gzip.open(nli_dataset_path, 'rt', encoding='utf8') as fIn:
            reader = csv.DictReader(fIn, delimiter='\t', quoting=csv.QUOTE_NONE)
            for row in reader:
                if row['split'] == 'train':
                    label_id = label2int[row['label']]
                    self.nli_train_samples.append(InputExample(texts=[row['sentence1'], row['sentence2']], label=label_id))
                    if len(self.nli_train_samples) >= max_train_samples:
                        break

        #Read STSB
        self.stsb_train_samples = []
        self.dev_samples = []
        self.test_samples = []
        with gzip.open(sts_dataset_path, 'rt', encoding='utf8') as fIn:
            reader = csv.DictReader(fIn, delimiter='\t', quoting=csv.QUOTE_NONE)
            for row in reader:
                score = float(row['score']) / 5.0  # Normalize score to range 0 ... 1
                inp_example = InputExample(texts=[row['sentence1'], row['sentence2']], label=score)

                if row['split'] == 'dev':
                    self.dev_samples.append(inp_example)
                elif row['split'] == 'test':
                    self.test_samples.append(inp_example)
                else:
                    self.stsb_train_samples.append(inp_example)

    def evaluate_stsb_test(self, model, expected_score):
        evaluator = EmbeddingSimilarityEvaluator.from_input_examples(self.test_samples, name='sts-test')
        score = model.evaluate(evaluator)*100
        print("STS-Test Performance: {:.2f} vs. exp: {:.2f}".format(score, expected_score))
        assert score > expected_score or abs(score-expected_score) < 0.1

    def _save_model(self):
        word_embedding_model = models.Transformer('distilbert-base-uncased')
        pooling_model = models.Pooling(word_embedding_model.get_word_embedding_dimension())
        model = SentenceTransformer(modules=[word_embedding_model, pooling_model])
        model.save(self.test_model_paths[0])

    def _test_save_optimizer(self):
        model = SentenceTransformer(self.test_model_paths[0])
        train_dataset = SentencesDataset(self.nli_train_samples[:10], model=model)
        train_dataloader = DataLoader(train_dataset, shuffle=True, batch_size=16)
        train_loss = losses.SoftmaxLoss(model=model, sentence_embedding_dimension=model.get_sentence_embedding_dimension(), num_labels=3)
        model.fit(train_objectives=[(train_dataloader, train_loss)],
                  evaluator=None,
                  epochs=1,
                  steps_per_epoch=5,
                  warmup_steps=int(len(train_dataloader) * 0.1),
                  checkpoint_save_steps=5,
                  checkpoint_path='./sample',
                  checkpoint_save_total_limit=1,
                  save_optimizer_scheduler=True,
                  use_amp=True)

    def test_load_optimizer(self):
        self._save_model()
        self._test_save_optimizer()
        model = SentenceTransformer(self.test_model_paths[1])
        train_dataset = SentencesDataset(self.nli_train_samples[:10], model=model)
        train_dataloader = DataLoader(train_dataset, shuffle=True, batch_size=16)
        train_loss = losses.SoftmaxLoss(model=model, sentence_embedding_dimension=model.get_sentence_embedding_dimension(), num_labels=3)
        model.fit(train_objectives=[(train_dataloader, train_loss)],
                  evaluator=None,
                  epochs=1,
                  steps_per_epoch=5,
                  warmup_steps=int(len(train_dataloader) * 0.1),
                  checkpoint_save_steps=5,
                  checkpoint_path='./sample',
                  checkpoint_save_total_limit=1,
                  save_optimizer_scheduler=True,
                  use_amp=True)
        try:
            for dir in self.test_model_paths:
                shutil.rmtree(dir)
        except OSError as e:
            print("Error: %s : %s" % (dir, e.strerror))


if "__main__" == __name__:
    unittest.main()
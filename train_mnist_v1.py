import os
import csv
import numpy as np
import seaborn as sns
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from torch.utils.data import DataLoader, random_split
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    precision_score,
    recall_score,
    f1_score,
    roc_curve,
    auc
)
from sklearn.preprocessing import label_binarize



# 1.定义 CNN 模型

class MNISTCNN(nn.Module):
    def __init__(self):
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 7 * 7, 128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, 10)
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x



# 2.数据集与 DataLoader

def build_dataloaders(data_root, train_size, val_size, train_batch_size, eval_batch_size):
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    full_train_dataset = torchvision.datasets.MNIST(
        root=data_root, train=True, download=True, transform=transform
    )
    test_dataset = torchvision.datasets.MNIST(
        root=data_root, train=False, download=True, transform=transform
    )

    train_dataset, val_dataset = random_split(full_train_dataset, [train_size, val_size])

    train_loader = DataLoader(train_dataset, batch_size=train_batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=eval_batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=eval_batch_size, shuffle=False)

    return train_loader, val_loader, test_loader



# 3.训练一个 epoch

def train_one_epoch(model, dataloader, loss_function, optimizer, device, print_interval=100):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (data, target) in enumerate(dataloader):
        data, target = data.to(device), target.to(device)

        optimizer.zero_grad()
        output = model(data)
        loss = loss_function(output, target)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()

        _, predicted = torch.max(output, dim=1)
        total += target.size(0)
        correct += (predicted == target).sum().item()

        if batch_idx % print_interval == 0 and batch_idx > 0:
            print(f'Batch [{batch_idx}/{len(dataloader)}], Loss: {running_loss / (batch_idx + 1):.4f}')

    epoch_loss = running_loss / len(dataloader)
    epoch_acc = 100.0 * correct / total
    return epoch_loss, epoch_acc



# 4.验证基础指标

def evaluate(model, dataloader, loss_function, device):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for data, target in dataloader:
            data, target = data.to(device), target.to(device)

            output = model(data)
            loss = loss_function(output, target)

            running_loss += loss.item()
            _, predicted = torch.max(output, dim=1)
            total += target.size(0)
            correct += (predicted == target).sum().item()

    epoch_loss = running_loss / len(dataloader)
    epoch_acc = 100.0 * correct / total
    return epoch_loss, epoch_acc


def evaluate_epoch_metrics(model, dataloader, loss_function, device):
    model.eval()
    running_loss = 0.0
    all_targets = []
    all_preds = []

    with torch.no_grad():
        for data, target in dataloader:
            data, target = data.to(device), target.to(device)

            output = model(data)
            loss = loss_function(output, target)

            running_loss += loss.item()
            _, predicted = torch.max(output, dim=1)

            all_targets.extend(target.cpu().numpy())
            all_preds.extend(predicted.cpu().numpy())

    all_targets = np.array(all_targets)
    all_preds = np.array(all_preds)

    epoch_loss = running_loss / len(dataloader)
    epoch_acc = 100.0 * (all_targets == all_preds).sum() / len(all_targets)
    precision_macro = precision_score(all_targets, all_preds, average='macro', zero_division=0)
    recall_macro = recall_score(all_targets, all_preds, average='macro', zero_division=0)
    f1_macro = f1_score(all_targets, all_preds, average='macro', zero_division=0)
    f1_weighted = f1_score(all_targets, all_preds, average='weighted', zero_division=0)

    return {
        "loss": epoch_loss,
        "acc": epoch_acc,
        "precision_macro": precision_macro,
        "recall_macro": recall_macro,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted
    }



# 5.详细测试评估

def evaluate_detailed(model, dataloader, loss_function, device, num_classes=10):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    all_targets = []
    all_preds = []
    all_probs = []
    all_images = []

    with torch.no_grad():
        for data, target in dataloader:
            data, target = data.to(device), target.to(device)

            output = model(data)
            loss = loss_function(output, target)

            probs = torch.softmax(output, dim=1)
            _, predicted = torch.max(probs, dim=1)

            running_loss += loss.item()
            total += target.size(0)
            correct += (predicted == target).sum().item()

            all_targets.extend(target.cpu().numpy())
            all_preds.extend(predicted.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())
            all_images.extend(data.cpu().numpy())

    epoch_loss = running_loss / len(dataloader)
    epoch_acc = 100.0 * correct / total

    all_targets = np.array(all_targets)
    all_preds = np.array(all_preds)
    all_probs = np.array(all_probs)
    all_images = np.array(all_images)
    all_confidences = np.max(all_probs, axis=1)

    precision_macro = precision_score(all_targets, all_preds, average='macro', zero_division=0)
    recall_macro = recall_score(all_targets, all_preds, average='macro', zero_division=0)
    f1_macro = f1_score(all_targets, all_preds, average='macro', zero_division=0)

    precision_weighted = precision_score(all_targets, all_preds, average='weighted', zero_division=0)
    recall_weighted = recall_score(all_targets, all_preds, average='weighted', zero_division=0)
    f1_weighted = f1_score(all_targets, all_preds, average='weighted', zero_division=0)

    cm = confusion_matrix(all_targets, all_preds)

    report_dict = classification_report(
        all_targets, all_preds, digits=4, zero_division=0, output_dict=True
    )
    report_text = classification_report(
        all_targets, all_preds, digits=4, zero_division=0
    )

    all_targets_bin = label_binarize(all_targets, classes=list(range(num_classes)))
    roc_auc_dict = {}
    fpr_dict = {}
    tpr_dict = {}

    for i in range(num_classes):
        fpr_dict[i], tpr_dict[i], _ = roc_curve(all_targets_bin[:, i], all_probs[:, i])
        roc_auc_dict[i] = auc(fpr_dict[i], tpr_dict[i])

    return {
        'loss': epoch_loss,
        'acc': epoch_acc,
        'precision_macro': precision_macro,
        'recall_macro': recall_macro,
        'f1_macro': f1_macro,
        'precision_weighted': precision_weighted,
        'recall_weighted': recall_weighted,
        'f1_weighted': f1_weighted,
        'confusion_matrix': cm,
        'classification_report_text': report_text,
        'classification_report_dict': report_dict,
        'all_targets': all_targets,
        'all_preds': all_preds,
        'all_probs': all_probs,
        'all_images': all_images,
        'all_confidences': all_confidences,
        'fpr_dict': fpr_dict,
        'tpr_dict': tpr_dict,
        'roc_auc_dict': roc_auc_dict
    }



# 6.保存辅助函数

def denormalize(img, mean=0.1307, std=0.3081):
    return img * std + mean


def save_metrics_to_txt(metrics, save_path):
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write("===== Final Test Result =====\n")
        f.write(f"Test Loss            : {metrics['loss']:.4f}\n")
        f.write(f"Test Accuracy        : {metrics['acc']:.2f}%\n")
        f.write(f"Precision (Macro)    : {metrics['precision_macro']:.4f}\n")
        f.write(f"Recall (Macro)       : {metrics['recall_macro']:.4f}\n")
        f.write(f"F1 Score (Macro)     : {metrics['f1_macro']:.4f}\n")
        f.write(f"Precision (Weighted) : {metrics['precision_weighted']:.4f}\n")
        f.write(f"Recall (Weighted)    : {metrics['recall_weighted']:.4f}\n")
        f.write(f"F1 Score (Weighted)  : {metrics['f1_weighted']:.4f}\n\n")
        f.write("===== Classification Report =====\n")
        f.write(metrics['classification_report_text'])


def save_classification_report_csv(report_dict, save_path):
    fieldnames = ["class", "precision", "recall", "f1-score", "support"]
    with open(save_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for key, value in report_dict.items():
            if isinstance(value, dict):
                writer.writerow([
                    key,
                    value.get("precision", ""),
                    value.get("recall", ""),
                    value.get("f1-score", ""),
                    value.get("support", "")
                ])


def save_training_log_csv(history, save_path):
    fieldnames = [
        "epoch",
        "train_loss", "train_acc",
        "val_loss", "val_acc",
        "val_precision_macro", "val_recall_macro",
        "val_f1_macro", "val_f1_weighted"
    ]
    with open(save_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in history:
            writer.writerow(row)



# 7.绘图函数

def plot_curves(train_losses, val_losses, train_accs, val_accs, save_dir):
    epochs = range(1, len(train_losses) + 1)

    plt.figure(figsize=(8, 6))
    plt.plot(epochs, train_losses, marker='o', label='Train Loss')
    plt.plot(epochs, val_losses, marker='o', label='Val Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.title('Loss Curve')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'loss_curve.png'), dpi=300)
    plt.close()

    plt.figure(figsize=(8, 6))
    plt.plot(epochs, train_accs, marker='o', label='Train Accuracy')
    plt.plot(epochs, val_accs, marker='o', label='Val Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy (%)')
    plt.title('Accuracy Curve')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'accuracy_curve.png'), dpi=300)
    plt.close()


def plot_f1_curves(val_f1_macros, val_f1_weighteds, save_dir):
    epochs = range(1, len(val_f1_macros) + 1)

    plt.figure(figsize=(8, 6))
    plt.plot(epochs, val_f1_macros, marker='o', label='Val Macro F1')
    plt.plot(epochs, val_f1_weighteds, marker='o', label='Val Weighted F1')
    plt.xlabel('Epoch')
    plt.ylabel('F1 Score')
    plt.title('Validation F1 Curves')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'f1_curve.png'), dpi=300)
    plt.close()


def plot_confusion_matrix(cm, class_names, save_dir):
    plt.figure(figsize=(8, 6))
    sns.heatmap(
        cm, annot=True, fmt='d', cmap='Blues',
        xticklabels=class_names, yticklabels=class_names
    )
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title('Confusion Matrix')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'confusion_matrix.png'), dpi=300)
    plt.close()

    np.savetxt(os.path.join(save_dir, 'confusion_matrix.csv'), cm, fmt='%d', delimiter=',')


def plot_roc_curves(fpr_dict, tpr_dict, roc_auc_dict, save_dir, num_classes=10):
    plt.figure(figsize=(10, 8))
    for i in range(num_classes):
        plt.plot(fpr_dict[i], tpr_dict[i], label=f'Class {i} (AUC = {roc_auc_dict[i]:.4f})')
    plt.plot([0, 1], [0, 1], linestyle='--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('ROC Curves (One-vs-Rest)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'roc_curves.png'), dpi=300)
    plt.close()


def plot_metric_bar(metrics, save_dir):
    names = ['Precision\n(Macro)', 'Recall\n(Macro)', 'F1\n(Macro)',
             'Precision\n(Weighted)', 'Recall\n(Weighted)', 'F1\n(Weighted)']
    values = [
        metrics['precision_macro'], metrics['recall_macro'], metrics['f1_macro'],
        metrics['precision_weighted'], metrics['recall_weighted'], metrics['f1_weighted']
    ]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(names, values)
    plt.ylim(0, 1.05)
    plt.ylabel('Score')
    plt.title('Overall Evaluation Metrics')
    for bar, v in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f'{v:.4f}', ha='center', va='bottom')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'overall_metrics_bar.png'), dpi=300)
    plt.close()


def plot_per_class_f1(report_dict, save_dir, num_classes=10):
    classes = [str(i) for i in range(num_classes)]
    f1_scores = [report_dict[str(i)]['f1-score'] for i in range(num_classes)]

    plt.figure(figsize=(8, 6))
    bars = plt.bar(classes, f1_scores)
    plt.ylim(0, 1.05)
    plt.xlabel('Class')
    plt.ylabel('F1 Score')
    plt.title('Per-Class F1 Score')
    for bar, v in zip(bars, f1_scores):
        plt.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f'{v:.3f}', ha='center', va='bottom')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'per_class_f1.png'), dpi=300)
    plt.close()


def plot_error_distribution(targets, preds, save_dir, num_classes=10):
    wrong_mask = targets != preds
    wrong_true_labels = targets[wrong_mask]

    if len(wrong_true_labels) == 0:
        print("没有误分类样本，跳过错误分布图。")
        return

    counts = np.bincount(wrong_true_labels, minlength=num_classes)

    plt.figure(figsize=(8, 6))
    bars = plt.bar([str(i) for i in range(num_classes)], counts)
    plt.xlabel('True Class')
    plt.ylabel('Number of Misclassified Samples')
    plt.title('Misclassification Distribution by True Class')
    for bar, v in zip(bars, counts):
        plt.text(bar.get_x() + bar.get_width() / 2, v + 0.1, str(int(v)), ha='center', va='bottom')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'error_distribution.png'), dpi=300)
    plt.close()


def plot_confidence_distribution(confidences, targets, preds, save_dir):
    correct_conf = confidences[targets == preds]
    wrong_conf = confidences[targets != preds]

    plt.figure(figsize=(8, 6))
    plt.hist(correct_conf, bins=30, alpha=0.7, label='Correct Predictions')
    plt.hist(wrong_conf, bins=30, alpha=0.7, label='Wrong Predictions')
    plt.xlabel('Prediction Confidence')
    plt.ylabel('Count')
    plt.title('Confidence Distribution')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'confidence_distribution.png'), dpi=300)
    plt.close()


def plot_misclassified_samples(images, targets, preds, save_dir, max_show=12):
    wrong_indices = np.where(targets != preds)[0]
    if len(wrong_indices) == 0:
        print("没有误分类样本。")
        return

    show_num = min(max_show, len(wrong_indices))
    cols = 4
    rows = int(np.ceil(show_num / cols))

    plt.figure(figsize=(12, 3 * rows))
    for i in range(show_num):
        idx = wrong_indices[i]
        img = denormalize(images[idx][0])

        plt.subplot(rows, cols, i + 1)
        plt.imshow(img, cmap='gray')
        plt.title(f'T:{targets[idx]} / P:{preds[idx]}')
        plt.axis('off')

    plt.suptitle('Misclassified Samples')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'misclassified_samples.png'), dpi=300)
    plt.close()


def plot_correct_samples(images, targets, preds, save_dir, max_show=12):
    correct_indices = np.where(targets == preds)[0]
    if len(correct_indices) == 0:
        print("没有正确分类样本。")
        return

    show_num = min(max_show, len(correct_indices))
    cols = 4
    rows = int(np.ceil(show_num / cols))

    plt.figure(figsize=(12, 3 * rows))
    for i in range(show_num):
        idx = correct_indices[i]
        img = denormalize(images[idx][0])

        plt.subplot(rows, cols, i + 1)
        plt.imshow(img, cmap='gray')
        plt.title(f'T:{targets[idx]} / P:{preds[idx]}')
        plt.axis('off')

    plt.suptitle('Correctly Classified Samples')
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'correct_samples.png'), dpi=300)
    plt.close()



# 8.主函数

def main():
    data_root = './Data_mnist'
    result_dir = './results_mnist_enhanced'
    model_save_path = './best_mnist_cnn.pth'

    train_size = 55000
    val_size = 5000

    train_batch_size = 64
    eval_batch_size = 1000

    learning_rate = 0.001
    epochs = 50
    random_seed = 42
    print_interval = 100

    num_classes = 10
    misclassified_show_num = 12
    correct_show_num = 12

    os.makedirs(result_dir, exist_ok=True)

    torch.manual_seed(random_seed)
    np.random.seed(random_seed)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')

    #  数据 
    train_loader, val_loader, test_loader = build_dataloaders(
        data_root=data_root,
        train_size=train_size,
        val_size=val_size,
        train_batch_size=train_batch_size,
        eval_batch_size=eval_batch_size
    )

    #  模型 
    model = MNISTCNN().to(device)
    loss_function = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    #  训练过程记录 
    train_losses = []
    val_losses = []
    train_accs = []
    val_accs = []
    val_f1_macros = []
    val_f1_weighteds = []
    training_history = []

    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        print(f'\n===== Epoch {epoch}/{epochs} =====')

        train_loss, train_acc = train_one_epoch(
            model=model,
            dataloader=train_loader,
            loss_function=loss_function,
            optimizer=optimizer,
            device=device,
            print_interval=print_interval
        )

        val_metrics = evaluate_epoch_metrics(
            model=model,
            dataloader=val_loader,
            loss_function=loss_function,
            device=device
        )

        val_loss = val_metrics["loss"]
        val_acc = val_metrics["acc"]
        val_f1_macro = val_metrics["f1_macro"]
        val_f1_weighted = val_metrics["f1_weighted"]

        train_losses.append(train_loss)
        val_losses.append(val_loss)
        train_accs.append(train_acc)
        val_accs.append(val_acc)
        val_f1_macros.append(val_f1_macro)
        val_f1_weighteds.append(val_f1_weighted)

        training_history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "train_acc": train_acc,
            "val_loss": val_loss,
            "val_acc": val_acc,
            "val_precision_macro": val_metrics["precision_macro"],
            "val_recall_macro": val_metrics["recall_macro"],
            "val_f1_macro": val_f1_macro,
            "val_f1_weighted": val_f1_weighted
        })

        print(f'Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}%')
        print(f'Val   Loss: {val_loss:.4f}, Val   Acc: {val_acc:.2f}%')
        print(f'Val Macro F1: {val_f1_macro:.4f}, Val Weighted F1: {val_f1_weighted:.4f}')

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), model_save_path)
            print(f'Best model saved to {model_save_path}')

    #  加载最佳模型并测试 
    model.load_state_dict(torch.load(model_save_path, map_location=device))

    test_metrics = evaluate_detailed(
        model=model,
        dataloader=test_loader,
        loss_function=loss_function,
        device=device,
        num_classes=num_classes
    )

    print('\n===== Final Test Result =====')
    print(f"Test Loss            : {test_metrics['loss']:.4f}")
    print(f"Test Accuracy        : {test_metrics['acc']:.2f}%")
    print(f"Precision (Macro)    : {test_metrics['precision_macro']:.4f}")
    print(f"Recall (Macro)       : {test_metrics['recall_macro']:.4f}")
    print(f"F1 Score (Macro)     : {test_metrics['f1_macro']:.4f}")
    print(f"Precision (Weighted) : {test_metrics['precision_weighted']:.4f}")
    print(f"Recall (Weighted)    : {test_metrics['recall_weighted']:.4f}")
    print(f"F1 Score (Weighted)  : {test_metrics['f1_weighted']:.4f}")

    print('\n===== Classification Report =====')
    print(test_metrics['classification_report_text'])

    #  保存文本/csv 
    save_metrics_to_txt(
        metrics=test_metrics,
        save_path=os.path.join(result_dir, 'test_metrics.txt')
    )
    save_classification_report_csv(
        report_dict=test_metrics['classification_report_dict'],
        save_path=os.path.join(result_dir, 'classification_report.csv')
    )
    save_training_log_csv(
        history=training_history,
        save_path=os.path.join(result_dir, 'training_log.csv')
    )

    #  保存图片 
    plot_curves(
        train_losses=train_losses,
        val_losses=val_losses,
        train_accs=train_accs,
        val_accs=val_accs,
        save_dir=result_dir
    )
    plot_f1_curves(
        val_f1_macros=val_f1_macros,
        val_f1_weighteds=val_f1_weighteds,
        save_dir=result_dir
    )
    plot_confusion_matrix(
        cm=test_metrics['confusion_matrix'],
        class_names=[str(i) for i in range(num_classes)],
        save_dir=result_dir
    )
    plot_roc_curves(
        fpr_dict=test_metrics['fpr_dict'],
        tpr_dict=test_metrics['tpr_dict'],
        roc_auc_dict=test_metrics['roc_auc_dict'],
        save_dir=result_dir,
        num_classes=num_classes
    )
    plot_metric_bar(
        metrics=test_metrics,
        save_dir=result_dir
    )
    plot_per_class_f1(
        report_dict=test_metrics['classification_report_dict'],
        save_dir=result_dir,
        num_classes=num_classes
    )
    plot_error_distribution(
        targets=test_metrics['all_targets'],
        preds=test_metrics['all_preds'],
        save_dir=result_dir,
        num_classes=num_classes
    )
    plot_confidence_distribution(
        confidences=test_metrics['all_confidences'],
        targets=test_metrics['all_targets'],
        preds=test_metrics['all_preds'],
        save_dir=result_dir
    )
    plot_misclassified_samples(
        images=test_metrics['all_images'],
        targets=test_metrics['all_targets'],
        preds=test_metrics['all_preds'],
        save_dir=result_dir,
        max_show=misclassified_show_num
    )
    plot_correct_samples(
        images=test_metrics['all_images'],
        targets=test_metrics['all_targets'],
        preds=test_metrics['all_preds'],
        save_dir=result_dir,
        max_show=correct_show_num
    )

    print(f"\n所有结果已保存到文件夹: {result_dir}")


if __name__ == '__main__':
    main()
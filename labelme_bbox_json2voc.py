"""
desc: gather json files annotated by labelme into a dictionary,
    and use this script to generate a voc style dataset.

reference: https://github.com/wkentaro/labelme/blob/main/examples/bbox_detection/labelme2voc.py
"""

# coding=utf-8

from __future__ import print_function

import argparse
import glob
import os
import os.path as osp
import re
import sys
from progressbar import ProgressBar
import labelme
import imgviz
from utils import get_label_conversion_dict

try:
    import lxml.builder
    import lxml.etree
except ImportError:
    print("Please install lxml:\n\n    pip install lxml\n")
    sys.exit(1)

# regex for get base name
pattern = re.compile(r"\d+")  # e.g. "擦花20180830172530对照样本.jpg" -> "20180830172530"


def get_base_name(file_name):
    """
    get base name per json file
    TODO: define the way generate base name.
    """
    # 1. use regex get item name

    # filename = osp.splitext(osp.basename(file_name))[0]
    # base = pattern.findall(filename)[0]

    # 2. just use original filename
    base = osp.splitext(osp.basename(file_name))[0]
    return base


def process_labels(label_file, label_dict, out_class_names_file):
    """get labels and save it to dataset dir"""
    class_names = []
    with open(label_file, "r", encoding="UTF-8") as label_f:
        for i, line in enumerate(label_f.readlines()):
            class_id = i - 1  # starts with -1
            class_name = line.strip()
            if class_id == -1:
                assert class_name == "__ignore__"
                continue
            if class_id == 0:
                assert class_name == "_background_"
            if class_name in label_dict:
                class_name = label_dict[class_name]
            class_names.append(class_name)

        class_names = tuple(class_names)
        print("class_names:", class_names)
        # save labels in txt for information
        with open(out_class_names_file, "w", encoding="UTF-8") as out_f:
            out_f.writelines("\n".join(class_names))
        print("Saved class_names:", out_class_names_file)
    return class_names


def get_bbox_boundaries(shape):
    """get box points
    TODO: define the way calculate box four point here.
    """
    # MARK: Please Confirm the box format in your dataset.
    # ⚠️：大家确认下自己使用的数据中 获取BBOX的方式正不正确。是否需要调整下标。

    # (xmin, ymin), (xmax, ymax) = shape["points"]

    xmin = shape['points'][0][0]
    ymin = shape['points'][0][1]
    xmax = shape['points'][2][0]
    ymax = shape['points'][2][1]
    # swap if min is larger than max.
    xmin, xmax = sorted([xmin, xmax])
    ymin, ymax = sorted([ymin, ymax])
    # be care of the difference between your dataset image Coordinate and labelme imgViz Coordinate.

    # return (xmin, ymin, xmax, ymax)

    return (ymin, xmin, ymax, xmax)


def process_annotated_json(class_names, filename, output_dir, label_dict):
    """translate to image and xml"""
    # file nam base
    base = get_base_name(filename)
    # src image file
    out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")
    # annotation xml file
    out_xml_file = osp.join(output_dir, "Annotations", base + ".xml")
    # visualize image file
    out_viz_file = osp.join(output_dir, "AnnotationsVisualization", base + ".jpg")

    label_file = labelme.LabelFile(filename=filename)

    # save source image
    img = labelme.utils.img_data_to_arr(label_file.imageData)
    imgviz.io.imsave(out_img_file, img)

    # generate voc format annotation file
    maker = lxml.builder.ElementMaker()
    xml = maker.annotation(
        # folder name
        maker.folder(""),
        # img path
        maker.filename(base + ".jpg"),
        # img source, ignore it
        maker.source(
            maker.database(""),
            maker.annotation(""),
            maker.image(""),
        ),
        # image size(height, width and channel)
        maker.size(
            maker.height(str(img.shape[0])),
            maker.width(str(img.shape[1])),
            maker.depth(str(img.shape[2])),
        ),
        # add category if it's for segmentation
        maker.segmented("0"),
    )

    # two list for visualization
    bboxes = []
    labels = []
    # MARK: change it for annotation shape type, some use points, some use rectangle.
    # Here shows the points one.
    for shape in label_file.shapes:
        box = get_bbox_boundaries(shape=shape)
        if box is None:
            continue

        class_name = shape["label"]  # object name in json file
        if class_name in label_dict:
            class_name = label_dict[class_name]
        class_id = class_names.index(class_name)  # convert to class id

        (xmin, ymin, xmax, ymax) = box
        bboxes.append([xmin, ymin, xmax, ymax])
        labels.append(class_id)

        xml.append(
            # object info
            maker.object(
                # label name
                maker.name(class_name),
                # pose info, ignore
                maker.pose(""),
                # truncated info, ignore
                maker.truncated("0"),
                # difficulty, ignore
                maker.difficult("0"),
                # bbox(up-left corner and bottom-right corner points)
                maker.bndbox(
                    maker.xmin(str(xmin)),
                    maker.ymin(str(ymin)),
                    maker.xmax(str(xmax)),
                    maker.ymax(str(ymax)),
                ),
            )
        )

    # caption for visualize drawing
    captions = [class_names[label] for label in labels]
    viz = imgviz.instances2rgb(
        image=img,
        labels=labels,
        bboxes=bboxes,
        captions=captions,
        font_size=15,
    )
    imgviz.io.imsave(out_viz_file, viz)

    # save voc annotation to xml file
    with open(out_xml_file, "wb") as out_f:
        out_f.write(lxml.etree.tostring(xml, pretty_print=True))


def main():
    """main"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("input_dir", help="input annotated directory")
    parser.add_argument("output_dir", help="output dataset directory")
    parser.add_argument("--labels", help="labels file", required=True)
    parser.add_argument("--label_dict", help="convert label with dict")
    args = parser.parse_args()

    # make voc format directory
    if osp.exists(args.output_dir):
        print("Output directory already exists:", args.output_dir)
        sys.exit(1)
    os.makedirs(args.output_dir)
    os.makedirs(osp.join(args.output_dir, "JPEGImages"))
    os.makedirs(osp.join(args.output_dir, "Annotations"))
    os.makedirs(osp.join(args.output_dir, "AnnotationsVisualization"))
    print("Creating dataset:", args.output_dir)
    # build label conversion dict
    fst2snd_dict = {}
    if args.label_dict:
        fst2snd_dict = get_label_conversion_dict(args.label_dict)

    # get labels and save it to dataset dir
    class_names = process_labels(label_file=args.labels,
                                 label_dict=fst2snd_dict,
                                 out_class_names_file=osp.join(args.output_dir, "class_names.txt"))

    label_file_list = glob.glob(osp.join(args.input_dir, "*.json"))
    pbar = ProgressBar().start()
    for i, filename in enumerate(label_file_list):
        process_annotated_json(class_names=class_names,
                               filename=filename,
                               output_dir=args.output_dir,
                               label_dict=fst2snd_dict)
        pbar.update(i + 1)
    pbar.finish()


if __name__ == "__main__":
    main()

from flask import Flask, request, send_file, abort
from werkzeug import secure_filename

app = Flask(__name__)
app.config.from_object('settings')
app.config.from_envvar('LYDON_SETTINGS')

import os
import shutil
import boto
from PIL import Image


EXT_TO_FORMAT = {
    'jpg': 'JPEG',
    'png': 'PNG',
}

FORMAT_TO_EXT = {
    'JPEG': 'jpg',
    'PNG': 'png',
}

EXT_TO_MIMETYPE = {
    'jpg': 'image/jpeg',
    'png': 'image/png',
}


@app.route('/', methods=['GET',])
def index():
    """Welcome page. Just for kicks. Does absolutely nothing."""
    return '<img src="http://media.digitalphotogallery.com/fvwxvyxzsjud/ima' \
           'ges/d9ce1e88-eb67-437d-8135-4779a6248cf4/john_lydon01_website_ima' \
           'ge_dywf_wuxga.jpg" style="height: 500px;" />', 200


@app.route('/<path:resource>', methods=['GET',])
def original(resource):
    """
    With no qualifiers, just returns resource object... with enhanced headers.
    """
    path = _get_resource_file(resource)
    image = Image.open(path)
    return _push_file(path,
                      EXT_TO_MIMETYPE[FORMAT_TO_EXT[image.format]],
                      _get_image_headers(image))


@app.route('/<path:resource>', methods=['POST', 'PUT',])
def create_or_update(resource):
    """
    Creates or updates resource. Purges cache if update.
    """
    s3 = boto.connect_s3(app.config['AWS_ACCESS_KEY_ID'],
                         app.config['AWS_SECRET_ACCESS_KEY'])
    bucket = s3.get_bucket(app.config['AWS_BUCKET'])
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    
    object = bucket.new_key(filename)
    object.set_contents_from_file(file)
    
    _flush(resource)
    
    return 'Created', 201


@app.route('/<path:resource>', methods=['DELETE',])
def delete(resource):
    """
    Deletes resource and any derivatives from system (and cache).
    """
    s3 = boto.connect_s3(app.config['AWS_ACCESS_KEY_ID'],
                         app.config['AWS_SECRET_ACCESS_KEY'])
    bucket = s3.get_bucket(app.config['AWS_BUCKET'])
    bucket.delete_key(resource)
    _flush(resource)
    return '', 204


@app.route('/<path:resource>-resized-<int:width>x', methods=['GET',])
@app.route('/<path:resource>-resized-x<int:height>', methods=['GET',])
@app.route('/<path:resource>-resized-<int:width>x<int:height>', methods=['GET',])
@app.route('/<path:resource>-resized-<int:width>x.<ext>', methods=['GET',])
@app.route('/<path:resource>-resized-x<int:height>.<ext>', methods=['GET',])
@app.route('/<path:resource>-resized-<int:width>x<int:height>.<ext>',
           methods=['GET',])
def resize(resource, width=None, height=None, ext=None):
    """
    Resizes resource object per specified qualifiers.
    """
    return _rescale(resource, width, height, ext, False)
    

@app.route('/<path:resource>-cropped-<int:width>x<int:height>', methods=['GET',])
@app.route('/<path:resource>-cropped-<int:width>x<int:height>.<ext>',
           methods=['GET',])
def crop(resource, width=None, height=None, ext=None):
    """
    Resizes and crops resource object per specified qualifiers.
    """
    return _rescale(resource, width, height, ext, True)
    
    
def _rescale(resource, width=None, height=None, ext=None, force=False):
    """
    Rescales the given image, optionally cropping it to make sure the result
    image has the specified width and height.
    (http://djangosnippets.org/snippets/224/)
    """
    image, width, height, ext = _populate_inputs(resource, width, height, ext)
    
    max_width = width
    max_height = height

    if not force:
        image.thumbnail((max_width, max_height), Image.ANTIALIAS)
    else:
        src_width, src_height = image.size
        src_ratio = float(src_width) / float(src_height)
        dst_width, dst_height = max_width, max_height
        dst_ratio = float(dst_width) / float(dst_height)
        
        if dst_ratio < src_ratio:
            crop_height = src_height
            crop_width = crop_height * dst_ratio
            x_offset = float(src_width - crop_width) / 2
            y_offset = 0
        else:
            crop_width = src_width
            crop_height = crop_width / dst_ratio
            x_offset = 0
            y_offset = float(src_height - crop_height) / 3
        image = image.crop((x_offset, y_offset, x_offset+int(crop_width),
                            y_offset+int(crop_height)))
        image = image.resize((dst_width, dst_height), Image.ANTIALIAS)

    path = os.path.join(_get_working_directory(), 'derivatives', request.path[1:])
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    
    image.save(path, EXT_TO_FORMAT[ext])
    
    return _push_file(path, EXT_TO_MIMETYPE[ext], _get_image_headers(image))
    

def _populate_inputs(resource, width=None, height=None, ext=None):
    """
    Populates missing inputs with original values.
    """
    image = Image.open(_get_resource_file(resource))

    width = width or image.size[0]
    height = height or image.size[1]
    ext = ext or FORMAT_TO_EXT[image.format]
    
    return image, width, height, ext


def _get_resource_file(resource):
    """
    Pulls resource file from S3 into working directory.
    """
    path = _get_local_file_path(resource)
    if os.path.exists(path):
        return path

    s3 = boto.connect_s3(app.config['AWS_ACCESS_KEY_ID'],
                         app.config['AWS_SECRET_ACCESS_KEY'])
    bucket = s3.get_bucket(app.config['AWS_BUCKET'])
    key = bucket.get_key(resource)

    if not key:
        abort(404)

    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

    key.get_contents_to_filename(path)

    return path


def _get_local_file_path(resource):
    """
    Builds a file path for local copy of resource file.
    """
    return os.path.join(_get_working_directory(), 'originals', resource)


def _get_working_directory():
    """
    Returns working directory.
    """
    return app.config['LYDON_WORKING_DIR']


def _get_image_headers(image):
    """
    Interrogates image and set custom HTTP headers.
    """
    aspect = _reduce_fraction(image.size[0], image.size[1])
    return {
        'X-Pixel-Width': image.size[0],
        'X-Pixel-Height': image.size[1],
        'X-Aspect-Ratio': '%sx%s' % (aspect[0], aspect[1]),
    }


def _flush(resource):
    queue = ['lydon/%s' % resource,]
    
    try:
        os.unlink(os.path.join(_get_working_directory(), 'originals', resource))
    except Exception, e:
        pass
    
    for item in os.listdir(os.path.join(_get_working_directory(), 'derivatives')):
        path = os.path.join(os.path.join(_get_working_directory(), 'derivatives'), item)
        try:
            if os.path.isfile(path) and item.startswith(resource):
                queue.append('lydon/%s' % item)
                os.unlink(path)
        except Exception, e:
            pass

    cloudfront = boto.connect_cloudfront(app.config['AWS_ACCESS_KEY_ID'], app.config['AWS_SECRET_ACCESS_KEY'])
    cloudfront.create_invalidation_request(app.config['AWS_DISTRIBUTION_ID'], queue)


def _push_file(path, mimetype, headers=None):
    """Pushes file stream to browser."""
    response = send_file(path, mimetype=mimetype, add_etags=False,
                         cache_timeout=app.config["LYDON_CACHE_TIMEOUT"])
    if headers:
        for header, value in headers.iteritems():
            response.headers.add(header, value)
    
    return response


def _reduce_fraction(n, d):
    """
    Reduces fractions. n is the numerator and d the denominator.
    """
    def _gcd(n, d):
        while d != 0:
            t = d
            d = n % d
            n = t
        return n
    assert d != 0, 'integer division by zero'
    assert isinstance(d, int), 'must be int'
    assert isinstance(n, int), 'must be int'
    greatest = _gcd(n, d)
    n /= greatest
    d /= greatest
    return n, d


if __name__ == '__main__':
    app.run()

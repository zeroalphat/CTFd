# -*- coding: utf-8 -*-
import logging
import os
import re
import time

from flask import current_app as app, render_template, request, redirect, url_for, session, Blueprint
from itsdangerous import TimedSerializer, BadTimeSignature, Signer, BadSignature
from passlib.hash import bcrypt_sha256

from CTFd.models import db, Teams
from CTFd import utils
from CTFd.utils import ratelimit
from flask import make_response
import base64

from CTFd.models import User
import util
import webauthn
from flask import jsonify
import sys

auth = Blueprint('auth', __name__)




RP_ID = 'localhost'
ORIGIN = 'https://localhost:4000'

# Trust anchors (trusted attestation roots) should be
# placed in TRUST_ANCHOR_DIR.
TRUST_ANCHOR_DIR = 'trusted_attestation_roots'

@auth.route('/confirm', methods=['POST', 'GET'])
@auth.route('/confirm/<data>', methods=['GET'])
@ratelimit(method="POST", limit=10, interval=60)
def confirm_user(data=None):
    if not utils.get_config('verify_emails'):
        # If the CTF doesn't care about confirming email addresses then redierct to challenges
        return redirect(url_for('challenges.challenges_view'))

    logger = logging.getLogger('regs')
    # User is confirming email account
    if data and request.method == "GET":
        try:
            s = TimedSerializer(app.config['SECRET_KEY'])
            email = s.loads(utils.base64decode(data), max_age=1800)
        except BadTimeSignature:
            return render_template('confirm.html', errors=['Your confirmation link has expired'])
        except (BadSignature, TypeError, base64.binascii.Error):
            return render_template('confirm.html', errors=['Your confirmation token is invalid'])
        team = Teams.query.filter_by(email=email).first_or_404()
        team.verified = True
        db.session.commit()
        logger.warn("[{date}] {ip} - {username} confirmed their account".format(
            date=time.strftime("%m/%d/%Y %X"),
            ip=utils.get_ip(),
            username=team.name.encode('utf-8'),
            email=team.email.encode('utf-8')
        ))
        db.session.close()
        if utils.authed():
            return redirect(url_for('challenges.challenges_view'))
        return redirect(url_for('auth.login'))

    # User is trying to start or restart the confirmation flow
    if not utils.authed():
        return redirect(url_for('auth.login'))

    team = Teams.query.filter_by(id=session['id']).first_or_404()

    if data is None:
        if request.method == "POST":
            # User wants to resend their confirmation email
            if team.verified:
                return redirect(url_for('views.profile'))
            else:
                utils.verify_email(team.email)
                logger.warn("[{date}] {ip} - {username} initiated a confirmation email resend".format(
                    date=time.strftime("%m/%d/%Y %X"),
                    ip=utils.get_ip(),
                    username=team.name.encode('utf-8'),
                    email=team.email.encode('utf-8')
                ))
            return render_template('confirm.html', team=team, infos=['Your confirmation email has been resent!'])
        elif request.method == "GET":
            # User has been directed to the confirm page
            team = Teams.query.filter_by(id=session['id']).first_or_404()
            if team.verified:
                # If user is already verified, redirect to their profile
                return redirect(url_for('views.profile'))
            return render_template('confirm.html', team=team)


@auth.route('/reset_password', methods=['POST', 'GET'])
@auth.route('/reset_password/<data>', methods=['POST', 'GET'])
@ratelimit(method="POST", limit=10, interval=60)
def reset_password(data=None):
    logger = logging.getLogger('logins')

    if data is not None:
        try:
            s = TimedSerializer(app.config['SECRET_KEY'])
            name = s.loads(utils.base64decode(data), max_age=1800)
        except BadTimeSignature:
            return render_template('reset_password.html', errors=['Your link has expired'])
        except (BadSignature, TypeError, base64.binascii.Error):
            return render_template('reset_password.html', errors=['Your reset token is invalid'])

        if request.method == "GET":
            return render_template('reset_password.html', mode='set')
        if request.method == "POST":
            team = Teams.query.filter_by(name=name).first_or_404()
            team.password = bcrypt_sha256.encrypt(request.form['password'].strip())
            db.session.commit()
            logger.warn("[{date}] {ip} -  successful password reset for {username}".format(
                date=time.strftime("%m/%d/%Y %X"),
                ip=utils.get_ip(),
                username=team.name.encode('utf-8')
            ))
            db.session.close()
            return redirect(url_for('auth.login'))

    if request.method == 'POST':
        email = request.form['email'].strip()
        team = Teams.query.filter_by(email=email).first()

        errors = []

        if utils.can_send_mail() is False:
            return render_template(
                'reset_password.html',
                errors=['Email could not be sent due to server misconfiguration']
            )

        if not team:
            return render_template(
                'reset_password.html',
                errors=['If that account exists you will receive an email, please check your inbox']
            )

        utils.forgot_password(email, team.name)

        return render_template(
            'reset_password.html',
            errors=['If that account exists you will receive an email, please check your inbox']
        )
    return render_template('reset_password.html')


@auth.route('/register', methods=['POST', 'GET'])
@ratelimit(method="POST", limit=10, interval=5)
def register():
    logger = logging.getLogger('regs')
    if not utils.can_register():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        errors = []
        
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        name_len = len(name) == 0
        names = Teams.query.add_columns('name', 'id').filter_by(name=name).first()
        emails = Teams.query.add_columns('email', 'id').filter_by(email=email).first()
        pass_short = len(password) == 0
        pass_long = len(password) > 128
        valid_email = utils.check_email_format(request.form['email'])
        team_name_email_check = utils.check_email_format(name)

        '''
        if not valid_email:
            errors.append("Please enter a valid email address")
        if names:
            errors.append('That team name is already taken')
        if team_name_email_check is True:
            errors.append('Your team name cannot be an email address')
        if emails:
            errors.append('That email has already been used')
        if pass_short:
            errors.append('Pick a longer password')
        if pass_long:
            errors.append('Pick a shorter password')
        if name_len:
            errors.append('Pick a longer team name')

        '''
        if len(errors) > 0:
            print("error occured", errors)
            return render_template('register.html', errors=errors, name=request.form['name'], email=request.form['email'], password=request.form['password'])
        
        if (len(password) == 0):
            with app.app_context():
                
                team = Teams(name, email.lower())
                db.session.add(team)
                db.session.commit()
                db.session.flush()
                

                session['username'] = name
                session['id'] = team.id
                session['register_username'] = name
                session['admin'] = team.admin
                session['nonce'] = utils.sha512(os.urandom(10))
                session['email'] =email.lower()
                

                rp_name = 'localhost'
                challenge = util.generate_challenge(32)
                ukey = util.generate_ukey()

                session['challenge'] = challenge
                session['register_ukey'] = ukey
                username = request.form['name']

                make_credential_options = webauthn.WebAuthnMakeCredentialOptions(
                   challenge, rp_name, RP_ID, ukey, username, username,
                   'https://example.com') 

                print('make_credential_options', make_credential_options.registration_dict)

                return jsonify(make_credential_options.registration_dict)
        else:
            with app.app_context():
                
                team = Teams(name, email.lower(), password)
                db.session.add(team)
                db.session.commit()
                db.session.flush()
                

                session['username'] = name
                session['id'] = team.id
                session['admin'] = team.admin
                session['nonce'] = utils.sha512(os.urandom(10))

                if utils.can_send_mail() and utils.get_config('verify_emails'):  # Confirming users is enabled and we can send email.
                    logger = logging.getLogger('regs')
                    logger.warn("[{date}] {ip} - {username} registered (UNCONFIRMED) with {email}".format(
                        date=time.strftime("%m/%d/%Y %X"),
                        ip=utils.get_ip(),
                        username=request.form['name'].encode('utf-8'),
                        email=request.form['email'].encode('utf-8')
                    ))
                    utils.verify_email(team.email)
                    db.session.close()
                    return redirect(url_for('auth.confirm_user'))
                else:  # Don't care about confirming users
                    if utils.can_send_mail():  # We want to notify the user that they have registered.
                        utils.sendmail(request.form['email'], "You've successfully registered for {}".format(utils.get_config('ctf_name')))

        logger.warn("[{date}] {ip} - {username} registered with {email}".format(
            date=time.strftime("%m/%d/%Y %X"),
            ip=utils.get_ip(),
            username=request.form['name'].encode('utf-8'),
            email=request.form['email'].encode('utf-8')
        ))
        db.session.close()
        return jsonify({"result": "password_success"})
        return redirect(url_for('challenges.challenges_view'))
    else:
        return render_template('register.html')

@auth.route('/fido2/complete', methods=['POST'])
def register_complete():

    challenge = session['challenge']
    ukey = session['register_ukey']
    username = session['username'] 
    registration_response = request.form

    trust_anchor_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), TRUST_ANCHOR_DIR)
    trusted_attestation_cert_required = True
    self_attestation_permitted = True
    none_attestation_permitted = True


    webauthn_registration_response = webauthn.WebAuthnRegistrationResponse(        
        RP_ID,
        ORIGIN,
        registration_response,
        challenge)  # User Verification


    try:
        webauthn_credential = webauthn_registration_response.verify()
        print("webautn_credential is success!")
    except Exception as e:
        print("error ocuuredd", e)
        return jsonify({'fail': 'Registration failed. Error: {}'.format(e)})


    
    # Step 17.
    #
    # Check that the credentialId is not yet registered to any other user.
    # If registration is requested for a credential that is already registered
    # to a different user, the Relying Party SHOULD fail this registration
    # ceremony, or it MAY decide to accept the registration, e.g. while deleting
    # the older registration.
    
    credential_id_exists = User.query.filter_by(
        credential_id=webauthn_credential.credential_id).first()
    if credential_id_exists:
        return make_response(
            jsonify({
                'fail': 'Credential ID already exists.'
            }), 401)

    existing_user = User.query.filter_by(username=username).first()
    if not existing_user:
        if sys.version_info >= (3, 0):
            webauthn_credential.credential_id = str(
                webauthn_credential.credential_id, "utf-8")
        user = User(
            ukey=ukey,
            username=username,
            display_name=username,
            pub_key=webauthn_credential.public_key,
            credential_id=webauthn_credential.credential_id,
            sign_count=webauthn_credential.sign_count,
            rp_id=RP_ID,
            icon_url='https://example.com')
        db.session.add(user)
        db.session.commit()
    else:
        return make_response(jsonify({'fail': 'User already exists.'}), 401)
    

    return jsonify({'success': 'User successfully registered.'})



@auth.route('/login', methods=['POST', 'GET'])
@ratelimit(method="POST", limit=10, interval=5)
def login():
    logger = logging.getLogger('logins')
    if request.method == 'POST':
        errors = []
        username = request.form['name']

        if not util.validate_username(username):
            return make_response(jsonify({'fail': 'Invalid username'}), 401)
        
        user = User.query.filter_by(username=username).first()

        if not user:
            return make_response(jsonify({'fail': 'User does not exits'}), 401)
        if not user.credential_id:
            return make_response(jsonify({'fail': 'Unknown credential ID.'}), 401)

        if 'challenge' in session:
            del session['challenge']
        
        challenge = util.generate_challenge(32)
        session['challenge'] = challenge

        
        webauthn_user = webauthn.WebAuthnUser(
            user.ukey, user.username, user.display_name, user.icon_url,
            user.credential_id, user.pub_key, user.sign_count, user.rp_id)

        webauthn_assertion_options = webauthn.WebAuthnAssertionOptions(
            webauthn_user, challenge)

        print(webauthn_assertion_options.assertion_dict)


        

        # Check if the user submitted an email address or a team name
        
        if utils.check_email_format(username) is True:
            team = Teams.query.filter_by(email=username).first()
        else:
            team = Teams.query.filter_by(name=username).first()

        # and bcrypt_sha256.verify(request.form['password'], team.password)
        if team:
            if team :
                try:
                    session.regenerate()  # NO SESSION FIXATION FOR YOU
                except:
                    pass  # TODO: Some session objects don't implement regenerate :(
                session['username'] = team.name
                session['id'] = team.id
                session['admin'] = team.admin
                session['nonce'] = utils.sha512(os.urandom(10))
                db.session.close()
                

                return jsonify(webauthn_assertion_options.assertion_dict)
                
                webauthn_user = webauthn.WebAuthnUser(    
                )

                logger.warn("[{date}] {ip} - {username} logged in".format(
                    date=time.strftime("%m/%d/%Y %X"),
                    ip=utils.get_ip(),
                    username=session['username'].encode('utf-8')
                ))

                if request.args.get('next') and utils.is_safe_url(request.args.get('next')):
                    return redirect(request.args.get('next'))
                return redirect(url_for('challenges.challenges_view'))

            else:  # This user exists but the password is wrong
                logger.warn("[{date}] {ip} - submitted invalid password for {username}".format(
                    date=time.strftime("%m/%d/%Y %X"),
                    ip=utils.get_ip(),
                    username=team.name.encode('utf-8')
                ))
                errors.append("Your username or password is incorrect")
                db.session.close()
                return render_template('login.html', errors=errors)

        else:  # This user just doesn't exist
            logger.warn("[{date}] {ip} - submitted invalid account information".format(
                date=time.strftime("%m/%d/%Y %X"),
                ip=utils.get_ip()
            ))
            errors.append("Your username or password is incorrect")
            db.session.close()
            return render_template('login.html', errors=errors)
    else:
        db.session.close()
        return render_template('login.html')


@app.route('/verify_assertion', methods=['POST'])
def verify_assertion():
    challenge = session.get('challenge')
    assertion_response = request.form
    credential_id = assertion_response.get('id')

    user = User.query.filter_by(credential_id=credential_id).first()
    if not user:
        return make_response(jsonify({'fail': 'User does not exist.'}), 401)

    webauthn_user = webauthn.WebAuthnUser(
        user.ukey, user.username, user.display_name, user.icon_url,
        user.credential_id, user.pub_key, user.sign_count, user.rp_id)

    webauthn_assertion_response = webauthn.WebAuthnAssertionResponse(
        webauthn_user,
        assertion_response,
        challenge,
        ORIGIN,
        uv_required=False)

    #session['id'] = assertion_response.get('id')

    try:
        sign_count = webauthn_assertion_response.verify()
    except Exception as e:
        return jsonify({'fail': 'Assertion failed. Error: {}'.format(e)})

    #Update counter
    user.sign_count = sign_count
    db.session.add(user)
    db.session.commit()

    return jsonify({
        'success':
        'Successfully authenticated as {}'.format(user.username)
    })

@app.route('/lastlogin', methods=['POST'])
def lastlogin():
    session['nonce'] = utils.sha512(os.urandom(10))
    if request.args.get('next') and utils.is_safe_url(request.args.get('next')):
        return redirect(request.args.get('next'))
    return redirect(url_for('challenges.challenges_view'))

@auth.route('/logout')
def logout():
    if utils.authed():
        session.clear()
    return redirect(url_for('views.static_html'))
